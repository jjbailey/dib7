#!/usr/bin/env python3
# bin/reconcile-catalog-openstack.py
# vim: set tabstop=4 shiftwidth=4 expandtab:

"""Remove OpenStack image-catalog entries when their images are gone."""

import argparse
import json
import os
from pathlib import Path

import keystoneauth1.exceptions
import openstack

from reconcile_catalog_common import (
    read_snapshot,
    read_vault,
    reconcile,
    report_credentials,
    select_vault_project,
    vault_projects,
)

def validate_openstack_environment(cloud):
    """Fail with actionable credentials guidance before connecting to OpenStack."""
    if cloud or os.environ.get("OS_CLOUD"):
        return

    required = {
        "OS_AUTH_URL": ("OS_AUTH_URL",),
        "OS_USERNAME or OS_USER_ID": ("OS_USERNAME", "OS_USER_ID"),
        "OS_PASSWORD or OS_TOKEN": ("OS_PASSWORD", "OS_TOKEN"),
        "OS_PROJECT_NAME or OS_PROJECT_ID": (
            "OS_PROJECT_NAME", "OS_PROJECT_ID"),
    }
    missing = [
        description for description, variables in required.items()
        if not any(os.environ.get(variable, "").strip() for variable in variables)
    ]
    if missing:
        raise ValueError(
            "missing required OpenStack environment variable(s): "
            + ", ".join(missing)
            + "; set the OS_* credentials, use --cloud with a configured "
            "clouds.yaml entry, or add the project to vaults/openstack.yml"
        )

def openstack_connection(vault_file, project, region_name, cloud=None):
    """--cloud, then OS_CLOUD / OS_* environment, then the vault entry.

    The vault entry is the openstack_projects one whose key, project_name,
    or project_id is the reconciled project (OPENSTACK_TARGET_PROJECT
    disambiguates, as for the import playbooks). It is used alone: an openrc
    or clouds.yaml for another project must not fill in what it leaves out.
    """
    connection_args = {"region_name": region_name} if region_name else {}
    if cloud:
        report_credentials("OpenStack", f"--cloud {cloud}")
        return openstack.connect(cloud=cloud, **connection_args)
    if os.environ.get("OS_CLOUD") or os.environ.get("OS_AUTH_URL"):
        validate_openstack_environment(None)
        report_credentials("OpenStack", "OS_* environment")
        return openstack.connect(**connection_args)
    document = read_vault(vault_file)
    selected = None
    legacy = None
    if document is not None:
        legacy = document.get("openstack_auth")
        if isinstance(legacy, dict) and not os.environ.get("OPENSTACK_TARGET_PROJECT", "").strip():
            selected = select_vault_project(
                {"legacy": legacy}, project, ("project_name", "project_id"),
                "OPENSTACK_TARGET_PROJECT", "openstack_projects")
        if selected is None:
            selected = select_vault_project(
                vault_projects(document, "openstack_projects"), project,
                ("project_name", "project_id"), "OPENSTACK_TARGET_PROJECT", "openstack_projects")
    if selected is None:
        validate_openstack_environment(None)  # raises with the usual guidance
    key, auth = selected
    options = {name: (str(value) if name == "project_id" else value)
               for name, value in auth.items() if value not in (None, "")}
    options.update(connection_args)
    source = (f"{Path(vault_file).name} openstack_auth" if auth is legacy
              else f"{Path(vault_file).name} openstack_projects[{key}]")
    report_credentials("OpenStack", source)
    return openstack.connect(load_envvars=False, load_yaml_config=False, **options)

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
    parser.add_argument("--cloud", help="clouds.yaml entry, instead of OS_* or the vault")
    parser.add_argument("--vault-file", type=Path, default=repo_dir / "vaults/openstack.yml",
                        help="encrypted vault holding openstack_projects credentials")
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

    vault_scope = str(args.project_id) if args.project_id else (
        next(iter(projects)) if len(projects) == 1 else None)
    connection = openstack_connection(args.vault_file, vault_scope, region_name, args.cloud)
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

    # Every path that reaches here has already failed when the requested project
    # did not match the authenticated one, so the scope is never empty: at
    # minimum it holds the explicitly requested project id.
    scope = projects & authenticated_identities
    if args.project_id:
        scope.add(str(args.project_id))

    def scope_match(image):
        if str(image.get("project", "")) not in scope:
            return False
        # The connection is region-scoped. A row recorded for another region
        # was not looked up, so it must not be removed. A row with no region
        # predates the field and stays in scope (see region_checkable).
        if region_name and has_region(image):
            return image.get("region") == region_name
        return True

    def has_region(image):
        recorded = image.get("region")
        return isinstance(recorded, str) and bool(recorded.strip())

    def region_checkable(image):
        # A row with no region may belong to another region, where its image
        # would look missing from here, so a region-scoped lookup must not
        # remove it. Retired rows go by status, so scope_match is enough.
        return scope_match(image) and (not region_name or has_region(image))

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
        if not region_checkable(image):
            print(
                f"skipping {image.get('logical_name')} {image.get('version')} "
                f"({image.get('artifact_id')}): no region recorded, so it is "
                f"not checked or removed from region {region_name}")
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
    reconcile(
        args.catalog, "openstack", stale, retired, region_checkable,
        authenticated_name or authenticated_id, args.dry_run, args.force,
    )

    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        openstack.exceptions.SDKException,
        keystoneauth1.exceptions.ClientException,
    ) as error:
        raise SystemExit(f"reconcile-catalog-openstack: {error}")
