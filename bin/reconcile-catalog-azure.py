#!/usr/bin/env python3
# bin/reconcile-catalog-azure.py
# vim: set tabstop=4 shiftwidth=4 expandtab:

"""Remove Azure catalog entries when their managed images are gone."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from azure.core.exceptions import AzureError, ResourceNotFoundError
from azure.identity import ClientSecretCredential, DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.core.tools import parse_resource_id

from reconcile_catalog_common import read_snapshot, reconcile

def _vault_password_file():
    """Use the same lookup as bin/edit-vault.sh, minus the prompt."""
    configured = os.environ.get("VAULT_PASSWORD_FILE")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_file():
            raise ValueError(f"VAULT_PASSWORD_FILE does not name a readable file: {path}")
        return path
    default = Path.home() / ".ssh" / "dib-vault-pass"
    return default if default.is_file() else None

def _ansible_vault_binary():
    venv_binary = Path(os.environ.get("DIB7_VENV_BIN", str(Path.home() / ".dib7" / "bin"))) / "ansible-vault"
    if venv_binary.is_file() and os.access(venv_binary, os.X_OK):
        return str(venv_binary)
    return shutil.which("ansible-vault")

def read_azure_vault(vault_file):
    """Return azure_projects from the encrypted vault.

    Returns None when the vault cannot be opened without prompting (no file,
    no password file, or no ansible-vault), so the caller can fall back.
    """
    if not vault_file.is_file():
        return None
    password_file = _vault_password_file()
    binary = _ansible_vault_binary()
    if password_file is None or binary is None:
        return None
    try:
        result = subprocess.run(
            [binary, "view", "--vault-password-file", str(password_file), str(vault_file)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        raise ValueError(
            f"ansible-vault could not decrypt {vault_file} (exit status {error.returncode})"
        ) from error
    import yaml

    document = yaml.safe_load(result.stdout)
    projects = document.get("azure_projects") if isinstance(document, dict) else None
    if not isinstance(projects, dict):
        raise ValueError(f"{vault_file} has no azure_projects mapping")
    return {str(key): entry for key, entry in projects.items() if isinstance(entry, dict)}

def select_vault_project(projects, subscription, requested=None):
    """Pick the azure_projects entry for this subscription.

    Mirrors playbooks/tasks/select-azure-project.yml: an explicit request
    (AZURE_TARGET_PROJECT) matches a vault key or subscription ID. Without
    one, the entry whose subscription_id is the reconciled subscription is
    used; None means the vault has no entry for it.
    """
    def entry_subscription(entry):
        return str(entry.get("subscription_id", "")).strip()

    if requested:
        matches = [(key, entry) for key, entry in projects.items()
                   if requested in (key, entry_subscription(entry))]
        if not matches:
            raise ValueError(
                f"AZURE_TARGET_PROJECT {requested!r} matches no key or subscription ID in "
                f"azure_projects; available: {', '.join(sorted(projects)) or '<none>'}")
    else:
        matches = [(key, entry) for key, entry in projects.items()
                   if entry_subscription(entry).lower() == subscription.lower()]
        if not matches:
            return None
    if len(matches) > 1:
        raise ValueError(
            f"several azure_projects entries match ({', '.join(sorted(key for key, _ in matches))}); "
            "set AZURE_TARGET_PROJECT to one key")
    key, entry = matches[0]
    if entry_subscription(entry).lower() != subscription.lower():
        raise ValueError(
            f"azure_projects[{key!r}] is for subscription {entry_subscription(entry)}, "
            f"not {subscription}")
    for field in ("tenant_id", "client_id", "client_secret"):
        if not str(entry.get(field) or "").strip():
            raise ValueError(f"azure_projects[{key!r}].{field} must be a non-empty string")
    return key, entry

def azure_credential(subscription, vault_file):
    """Choose credentials: AZURE_* environment, then the vault, then az login.

    The playbook passes AZURE_TENANT/AZURE_CLIENT_ID/AZURE_SECRET; the Azure
    SDK's EnvironmentCredential spells them AZURE_TENANT_ID and
    AZURE_CLIENT_SECRET. Accept either. Otherwise use the service principal
    the import playbook uses, from vaults/azure.yml. DefaultAzureCredential
    (az login, managed identity) is the last resort; Entra ID security
    defaults can block az login for interactive users.
    """
    tenant = os.environ.get("AZURE_TENANT") or os.environ.get("AZURE_TENANT_ID")
    client_id = os.environ.get("AZURE_CLIENT_ID")
    secret = os.environ.get("AZURE_SECRET") or os.environ.get("AZURE_CLIENT_SECRET")
    if tenant and client_id and secret:
        print("Azure credentials: service principal from AZURE_* environment", file=sys.stderr)
        return ClientSecretCredential(tenant, client_id, secret)

    projects = read_azure_vault(vault_file)
    if projects is not None:
        requested = os.environ.get("AZURE_TARGET_PROJECT", "").strip() or None
        selected = select_vault_project(projects, subscription, requested)
        if selected is not None:
            key, entry = selected
            print(f"Azure credentials: service principal from {vault_file.name} "
                  f"azure_projects[{key}]", file=sys.stderr)
            return ClientSecretCredential(
                str(entry["tenant_id"]).strip(),
                str(entry["client_id"]).strip(),
                str(entry["client_secret"]).strip(),
            )

    print("Azure credentials: DefaultAzureCredential (az login, managed identity)", file=sys.stderr)
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
