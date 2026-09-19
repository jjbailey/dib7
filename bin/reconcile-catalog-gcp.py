#!/usr/bin/env python3
# bin/reconcile-catalog-gcp.py
# vim: set tabstop=4 shiftwidth=4 expandtab:



"""Remove GCP catalog entries when their images are gone."""

import argparse
import json
from pathlib import Path

import google.auth
from google.auth.transport.requests import AuthorizedSession

from reconcile_catalog_common import read_snapshot, reconcile


def main():
    repo_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path,
                        default=repo_dir / "catalogs/image-catalog.json")
    parser.add_argument("--project")
    parser.add_argument("--credentials-file", type=Path)
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
    credentials_args = {"scopes": [
        "https://www.googleapis.com/auth/cloud-platform"]}
    if args.credentials_file:
        credentials, _ = google.auth.load_credentials_from_file(
            args.credentials_file, **credentials_args)
    else:
        credentials, _ = google.auth.default(**credentials_args)
    session = AuthorizedSession(credentials)
    def scope_match(image): return image.get("project") == project
    retired = [image for image in catalog["images"] if image.get(
        "provider") == "gcp" and image.get("status") == "retired" and scope_match(image)]
    stale = []
    for image in catalog["images"]:
        if image.get("provider") != "gcp" or image.get("status") != "published" or not scope_match(image):
            continue
        response = session.get(image["artifact_id"])
        if response.status_code == 404:
            stale.append((image, "image not found"))
        else:
            response.raise_for_status()
    print(f"GCP scope: project={project}")
    return reconcile(args.catalog, "gcp", stale, retired, scope_match, project, args.dry_run, args.force)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"reconcile-catalog-gcp: {error}")
