#!/usr/bin/env python3
# reconcile-catalog-openstack.py
# vim: set tabstop=4 shiftwidth=4 expandtab:

"""Remove OpenStack catalog entries when their images are gone."""

import argparse
import json
from pathlib import Path

import openstack

from reconcile_catalog_common import read_snapshot, reconcile


def main():
    repo_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path,
                        default=repo_dir / "catalogs/image-catalog.json")
    parser.add_argument("--cloud")
    parser.add_argument("--project-id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    catalog = read_snapshot(args.catalog)
    projects = {image.get("project") for image in catalog["images"] if image.get(
        "provider") == "openstack" and image.get("project")}
    if not projects and not args.project_id:
        print("no OpenStack catalog entries found")
        return 0
    connection_args = {"cloud": args.cloud} if args.cloud else {}
    connection = openstack.connect(**connection_args)
    authenticated_project = connection.current_project_id
    project = args.project_id or authenticated_project or (
        next(iter(projects)) if len(projects) == 1 else None)
    if not project:
        raise ValueError(
            "could not determine OpenStack project; provide --project-id")
    if authenticated_project and authenticated_project != project:
        raise ValueError(
            f"authenticated OpenStack project {authenticated_project} does not match project {project}")

    def scope_match(image): return image.get("project") == project
    retired = [image for image in catalog["images"] if image.get(
        "provider") == "openstack" and image.get("status") == "retired" and scope_match(image)]
    stale = []
    for image in catalog["images"]:
        if image.get("provider") != "openstack" or image.get("status") != "published" or not scope_match(image):
            continue
        try:
            if connection.get_image(image["artifact_id"]) is None:
                stale.append((image, "image not found"))
        except openstack.exceptions.NotFoundException:
            stale.append((image, "image not found"))
    print(f"OpenStack scope: project={project}")
    return reconcile(args.catalog, "openstack", stale, retired, scope_match, project, args.dry_run, args.force)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError, openstack.exceptions.SDKException) as error:
        raise SystemExit(f"reconcile-catalog-openstack: {error}")
