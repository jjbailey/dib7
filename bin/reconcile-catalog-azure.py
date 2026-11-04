#!/usr/bin/env python3
# bin/reconcile-catalog-azure.py
# vim: set tabstop=4 shiftwidth=4 expandtab:

"""Remove Azure catalog entries when their managed images are gone."""

import argparse
import json
import os
from pathlib import Path

from azure.core.exceptions import AzureError, ResourceNotFoundError
from azure.identity import ClientSecretCredential, DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.core.tools import parse_resource_id

from reconcile_catalog_common import (
    read_snapshot,
    read_vault,
    reconcile,
    report_credentials,
    require_fields,
    select_vault_project,
    vault_projects,
)

def azure_credential(subscription, vault_file):
    """Choose credentials: AZURE_* environment, then the vault, then az login.

    The playbook passes AZURE_TENANT/AZURE_CLIENT_ID/AZURE_SECRET; the Azure
    SDK's EnvironmentCredential spells them AZURE_TENANT_ID and
    AZURE_CLIENT_SECRET. Accept either. Otherwise use the service principal
    the import playbook uses, from vaults/azure.yml (AZURE_TARGET_PROJECT
    disambiguates, as for the import playbooks). DefaultAzureCredential
    (az login, managed identity) is the last resort; Entra ID security
    defaults can block az login for interactive users.
    """
    tenant = os.environ.get("AZURE_TENANT") or os.environ.get("AZURE_TENANT_ID")
    client_id = os.environ.get("AZURE_CLIENT_ID")
    secret = os.environ.get("AZURE_SECRET") or os.environ.get("AZURE_CLIENT_SECRET")
    if tenant and client_id and secret:
        report_credentials("Azure", "service principal from AZURE_* environment")
        return ClientSecretCredential(tenant, client_id, secret)

    document = read_vault(vault_file)
    if document is not None:
        selected = select_vault_project(
            vault_projects(document, "azure_projects"), subscription,
            ("subscription_id",), "AZURE_TARGET_PROJECT", "azure_projects")
        if selected is not None:
            key, entry = selected
            require_fields("azure_projects", key, entry, ("tenant_id", "client_id", "client_secret"))
            report_credentials("Azure", f"service principal from {vault_file.name} azure_projects[{key}]")
            return ClientSecretCredential(
                str(entry["tenant_id"]).strip(),
                str(entry["client_id"]).strip(),
                str(entry["client_secret"]).strip(),
            )

    report_credentials("Azure", "DefaultAzureCredential (az login, managed identity)")
    return DefaultAzureCredential()

def main():
    repo_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path,
                        default=repo_dir / "catalogs/image-catalog.json")
    parser.add_argument("--subscription", "--project", dest="subscription",
                        help="only reconcile this Azure subscription ID")
    parser.add_argument("--vault-file", type=Path, default=repo_dir / "vaults/azure.yml",
                        help="encrypted vault holding azure_projects service principals")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    catalog = read_snapshot(args.catalog)
    subscriptions = {image.get("project") for image in catalog["images"] if image.get(
        "provider") == "azure" and image.get("project")}
    if not subscriptions and not args.subscription:
        print("no Azure catalog entries found")
        return 0
    subscription = args.subscription or (
        next(iter(subscriptions)) if len(subscriptions) == 1 else None)
    if not subscription:
        raise ValueError(
            "catalog contains multiple Azure subscriptions; provide --subscription")
    subscription = str(subscription)

    def scope_match(image): return image.get("project") == subscription
    retired = [image for image in catalog["images"] if image.get(
        "provider") == "azure" and image.get("status") == "retired" and scope_match(image)]
    published = [image for image in catalog["images"] if image.get(
        "provider") == "azure" and image.get("status") == "published" and scope_match(image)]
    stale = []
    if published:
        client = ComputeManagementClient(azure_credential(subscription, args.vault_file), subscription)
        for image in published:
            parts = parse_resource_id(image["artifact_id"])
            # The artifact ID names its own subscription. A row whose ID
            # disagrees with its project column is malformed; refuse rather
            # than look it up with credentials for the wrong subscription.
            if str(parts.get("subscription", "")).lower() != subscription.lower():
                raise ValueError(
                    f"{image['artifact_id']} is not in subscription {subscription}")
            try:
                client.images.get(parts["resource_group"], parts["name"])
            except ResourceNotFoundError:
                stale.append((image, "image not found"))
    print(f"Azure scope: subscription={subscription}")
    reconcile(args.catalog, "azure", stale, retired, scope_match, subscription, args.dry_run, args.force)

    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        OSError,
        ValueError,
        KeyError,
        json.JSONDecodeError,
        AzureError,
    ) as error:
        raise SystemExit(f"reconcile-catalog-azure: {error}")
