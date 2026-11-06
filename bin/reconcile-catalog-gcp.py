#!/usr/bin/env python3
# bin/reconcile-catalog-gcp.py
# vim: set tabstop=4 shiftwidth=4 expandtab:

"""Remove GCP catalog entries when their images are gone."""

import argparse
import json
import os
from pathlib import Path

import google.auth
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account
import requests

from reconcile_catalog_common import (
    read_snapshot,
    read_vault,
    reconcile,
    report_credentials,
    select_vault_project,
    vault_projects,
)

SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]

def gcp_credentials(project, vault_file, credentials_file=None):
    """--credentials-file, then GOOGLE_APPLICATION_CREDENTIALS, then the vault,
    then the remaining Google defaults (gcloud login, metadata server).

    The vault entry is the gcp_projects one whose key or gcp_project is the
    reconciled project (GCP_TARGET_PROJECT disambiguates, as for the import
    playbooks); its service_account_key authenticates.

    Returns (credentials, the project the credentials carry).
    """
    if credentials_file:
        report_credentials("GCP", f"--credentials-file {credentials_file}")
        return google.auth.load_credentials_from_file(credentials_file, scopes=SCOPES)
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip():
        report_credentials("GCP", "GOOGLE_APPLICATION_CREDENTIALS environment")
        return google.auth.default(scopes=SCOPES)
    document = read_vault(vault_file)
    if document is not None:
        legacy = document if str(document.get("gcp_project") or "").strip() else None
        if legacy and not os.environ.get("GCP_TARGET_PROJECT", "").strip() and (
                str(legacy["gcp_project"]).strip().lower() == str(project).strip().lower()):
            selected = ("legacy", legacy)
        else:
            selected = select_vault_project(
                vault_projects(document, "gcp_projects"), project,
                ("gcp_project", "project_id"), "GCP_TARGET_PROJECT", "gcp_projects")
        if selected is not None:
            key, entry = selected
            entry_name = "legacy gcp_project" if entry is legacy else f"gcp_projects[{key!r}]"
            raw = entry.get("service_account_key")
            try:
                info = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"{entry_name}.service_account_key is not valid JSON: {error}") from error
            if not info.get("client_email"):
                raise ValueError(f"{entry_name}.service_account_key has no client_email")
            source = (f"{Path(vault_file).name} legacy" if entry is legacy
                      else f"{Path(vault_file).name} gcp_projects[{key}]")
            report_credentials("GCP", f"service account from {source}")
            credentials = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
            return credentials, info.get("project_id")
    report_credentials("GCP", "Google application default credentials (gcloud, metadata server)")
    return google.auth.default(scopes=SCOPES)

def main():
    repo_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path,
                        default=repo_dir / "catalogs/image-catalog.json")
    parser.add_argument("--project")
    parser.add_argument("--credentials-file", type=Path,
                        help="service-account JSON, instead of the environment or the vault")
    parser.add_argument("--vault-file", type=Path, default=repo_dir / "vaults/gcp.yml",
                        help="encrypted vault holding gcp_projects service accounts")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    catalog = read_snapshot(args.catalog)
    projects = {image.get("project") for image in catalog["images"] if image.get(
        "provider") == "gcp" and image.get("project")}
    if not projects and not args.project:
        print("no GCP catalog entries found")
        return 0
    project = args.project or (
        next(iter(projects)) if len(projects) == 1 else None)
    if not project:
        raise ValueError(
            "catalog contains multiple GCP projects; provide --project")
    def scope_match(image): return image.get("project") == project
    retired = [image for image in catalog["images"] if image.get(
        "provider") == "gcp" and image.get("status") == "retired" and scope_match(image)]
    published = [image for image in catalog["images"] if image.get(
        "provider") == "gcp" and image.get("status") == "published" and scope_match(image)]
    stale = []
    if published:
        credentials, credential_project = gcp_credentials(
            project, args.vault_file, args.credentials_file)
        credential_project = credential_project or getattr(credentials, "project_id", None)
        if credential_project and str(credential_project) != str(project):
            raise ValueError(
                f"resolved GCP credentials belong to project {credential_project}, not --project {project}")
        session = AuthorizedSession(credentials)
    for image in published:
        response = session.get(image["artifact_id"])
        if response.status_code == 404:
            stale.append((image, "image not found"))
        else:
            response.raise_for_status()
    print(f"GCP scope: project={project}")
    reconcile(args.catalog, "gcp", stale, retired, scope_match, project, args.dry_run, args.force)

    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        requests.exceptions.RequestException,
    ) as error:
        raise SystemExit(f"reconcile-catalog-gcp: {error}")
