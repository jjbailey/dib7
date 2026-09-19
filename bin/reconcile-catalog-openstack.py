#!/usr/bin/env python3
# bin/reconcile-catalog-openstack.py
# vim: set tabstop=4 shiftwidth=4 expandtab:



"""Remove OpenStack image-catalog entries when their images are gone."""

import argparse
import json
from pathlib import Path

import openstack

from reconcile_catalog_common import read_snapshot, reconcile


def project_name(connection):
    try:
        return str(connection.current_project.name)
    except (AttributeError, TypeError, openstack.exceptions.SDKException):
        return None


def main():
    repo_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path,
                        default=repo_dir / "catalogs/image-catalog.json")
    parser.add_argument("--cloud")
    parser.add_argument("--region-name")
    parser.add_argument(
        "--project-id",
        help="OpenStack project name or ID; required when the catalog has multiple projects",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    catalog = read_snapshot(args.catalog)
    projects = {
        str(image.get("project"))
        for image in catalog["images"]
        if image.get("provider") == "openstack" and image.get("project")
    }
    if not projects and not args.project_id:
        print("no OpenStack catalog entries found")
        return 0

    region_names = {
        str(image.get("region"))
        for image in catalog["images"]
        if image.get("provider") == "openstack"
        and image.get("region")
    }
    if args.region_name:
        region_name = args.region_name
    elif len(region_names) == 1:
        region_name = next(iter(region_names))
    elif len(region_names) > 1:
        raise ValueError(
            "catalog contains multiple OpenStack regions; provide --region-name")
    else:
        region_name = None

    connection_args = {}
    if args.cloud:
        connection_args["cloud"] = args.cloud
    if region_name:
        connection_args["region_name"] = region_name
    connection = openstack.connect(**connection_args)
    authenticated_id = connection.current_project_id
    authenticated_name = project_name(connection)
    authenticated_identities = {str(value) for value in (
        authenticated_id, authenticated_name) if value}

    if args.project_id:
        requested = str(args.project_id)
        if requested not in authenticated_identities:
            raise ValueError(
                f"authenticated OpenStack project {authenticated_id} does not match "
                f"--project-id {args.project_id}"
            )
    else:
        matching = projects & authenticated_identities
        if len(projects) > 1 and not matching:
            raise ValueError(
                "catalog contains multiple OpenStack projects; provide --project-id"
            )
        if len(projects) == 1 and not matching:
            raise ValueError(
                f"catalog contains no entry for authenticated project {authenticated_id}"
            )

    scope = projects & authenticated_identities
    if args.project_id:
        scope.add(str(args.project_id))
    if not scope:
        raise ValueError(
            f"catalog contains no entry for authenticated project {authenticated_id}"
        )

    def scope_match(image):
        return str(image.get("project", "")) in scope

    retired = [
        image for image in catalog["images"]
        if image.get("provider") == "openstack"
        and image.get("status") == "retired"
        and scope_match(image)
    ]
    stale = []
    for image in catalog["images"]:
        if image.get("provider") != "openstack" or image.get("status") != "published" or not scope_match(image):
            continue
        try:
            if connection.get_image(image["artifact_id"]) is None:
                stale.append((image, "image not found"))
        except openstack.exceptions.NotFoundException:
            stale.append((image, "image not found"))

    print(
        f"OpenStack scope: project={authenticated_name or authenticated_id}"
        + (f", region={region_name}" if region_name else "")
    )
    return reconcile(
        args.catalog, "openstack", stale, retired, scope_match,
        authenticated_name or authenticated_id, args.dry_run, args.force,
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError, openstack.exceptions.SDKException) as error:
        raise SystemExit(f"reconcile-catalog-openstack: {error}")
