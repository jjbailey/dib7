#!/usr/bin/env python3
# bin/reconcile-catalog-vsphere.py
# vim: set tabstop=4 shiftwidth=4 expandtab:

"""Remove vSphere catalog entries whose artifacts are gone."""
from __future__ import annotations
import argparse
import json
import os
import subprocess
from pathlib import Path
from reconcile_catalog_common import read_snapshot, read_vault, reconcile, report_credentials

CREDENTIAL_FIELDS = ("vcenter_hostname", "vcenter_username", "vcenter_password")

POWERSHELL_QUERY = r"""
$ErrorActionPreference = 'Stop'
$password = ConvertTo-SecureString ([Console]::In.ReadLine()) -AsPlainText -Force
$credential = [PSCredential]::new($env:vcenter_username, $password)
$server = $env:vcenter_hostname
$library = $env:vsphere_catalog_library
Connect-VIServer -Server $server -Credential $credential | Out-Null
try {
  $contentLibrary = Get-ContentLibrary -Name $library
  $items = @(Get-ContentLibraryItem -ContentLibrary $contentLibrary | ForEach-Object { [string]$_.Name })
  $templates = @(Get-Template | ForEach-Object { [string]$_.Name })
  [pscustomobject]@{ library_items = $items; templates = $templates } | ConvertTo-Json -Compress
} finally {
  Disconnect-VIServer -Server $server -Confirm:$false | Out-Null
}
"""

def vault_vcenter(document, vcenter):
    """The vsphere.yml credentials for a catalog vCenter label, or None.

    The label is what select-vcenter.yml recorded: a vsphere_projects key, or
    "legacy" for the flat vcenter_* mapping. Rows with no label predate it;
    like select-vcenter.yml with no request, they take the flat mapping, else
    a single vsphere_projects entry.
    """
    projects = {str(key): entry for key, entry in (document.get("vsphere_projects") or {}).items()
                if isinstance(entry, dict)}
    flat = document if str(document.get("vcenter_hostname") or "").strip() else None
    if vcenter == "legacy":
        return ("legacy", flat) if flat else None
    if vcenter:
        return (vcenter, projects[vcenter]) if vcenter in projects else None
    if flat:
        return "legacy", flat
    if len(projects) == 1:
        return next(iter(projects.items()))
    return None

def vcenter_environment(vcenter, vault_file):
    """vcenter_* environment for PowerCLI: exported values, else the vault.

    vcenter_hostname/vcenter_username/vcenter_password (or the VCENTER_*
    spellings) win when all three are exported. Otherwise the vault entry
    for the reconciled vCenter supplies them.
    """
    exported = {name: os.environ.get(name) or os.environ.get(name.upper()) for name in CREDENTIAL_FIELDS}
    if all(exported.values()):
        report_credentials("vSphere", "vcenter_* environment")
        return exported
    document = read_vault(vault_file) if vault_file else None
    selected = vault_vcenter(document, vcenter) if document is not None else None
    if selected is None:
        missing = [name for name, value in exported.items() if not value]
        raise ValueError(
            "missing vCenter environment variable(s): " + ", ".join(missing)
            + f"; or add vCenter {vcenter or '(unscoped)'} to {Path(vault_file).name}")
    key, entry = selected
    values = {name: str(entry.get(name) or "") for name in CREDENTIAL_FIELDS}
    missing = [name for name, value in values.items() if not value.strip()]
    if missing:
        raise ValueError(f"vsphere.yml {key} is missing {', '.join(missing)}")
    report_credentials("vSphere", f"{Path(vault_file).name} {key}")
    return values

def query_live_artifacts(library, vcenter=None, vault_file=None):
    credentials = vcenter_environment(vcenter, vault_file)
    env = os.environ.copy()
    env.update(credentials)
    # The password reaches PowerCLI on stdin, not in pwsh's environment.
    for name in ("vcenter_password", "VCENTER_PASSWORD"):
        env.pop(name, None)
    env["vsphere_catalog_library"] = library
    result = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-Command", POWERSHELL_QUERY],
                            input=credentials["vcenter_password"] + "\n",
                            capture_output=True, text=True, check=True, env=env)
    try:
        document = json.loads(result.stdout.strip())
    except json.JSONDecodeError as error:
        raise ValueError(f"PowerCLI returned invalid JSON: {error}") from error
    return set(document.get("library_items", [])), set(document.get("templates", []))

def main():
    repo_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path,
                        default=repo_dir / "catalogs/image-catalog.json")
    parser.add_argument("--library")
    parser.add_argument("--vcenter", help="only reconcile entries for this vCenter key/hostname")
    parser.add_argument("--vault-file", type=Path, default=repo_dir / "vaults/vsphere.yml",
                        help="encrypted vault holding vCenter credentials")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    catalog = read_snapshot(args.catalog)
    def vsphere_images():
        return [image for image in catalog["images"] if image.get("provider") == "vsphere"]

    libraries = {image.get("scope", {}).get("content_library") for image in vsphere_images()
                 if image.get("scope", {}).get("content_library")}
    vcenters = {image.get("scope", {}).get("vcenter") for image in vsphere_images()
                if image.get("scope", {}).get("vcenter")}
    if not libraries:
        print("no vSphere catalog entries found")
        return 0
    library = args.library or (
        next(iter(libraries)) if len(libraries) == 1 else None)
    if not library:
        raise ValueError(
            "catalog contains multiple vSphere content libraries; provide --library")
    # A row with no scope.vcenter is not "every vCenter". Auto-selecting the
    # one recorded vCenter used to treat that missing field as in-scope and
    # delete the unscoped twin without querying it. A named --vcenter reconciles
    # only rows that record that vCenter. Omit --vcenter to reconcile the
    # unscoped rows, and only when they are the only rows in the library.
    library_rows = [
        image for image in vsphere_images()
        if (image.get("scope") or {}).get("content_library") == library
    ]
    unscoped = [image for image in library_rows if not (image.get("scope") or {}).get("vcenter")]
    if args.vcenter:
        vcenter = args.vcenter
        if vcenter not in vcenters:
            raise ValueError(
                f"catalog contains no vSphere entries for vCenter {vcenter}; "
                "--vcenter selects the catalog label (a vault key, or legacy), "
                "not vcenter_hostname. recorded: "
                + (", ".join(sorted(vcenters)) or "<none>"))
    elif unscoped and vcenters:
        raise ValueError(
            "catalog mixes vSphere entries that name a vCenter with entries "
            "that do not; pass --vcenter to reconcile the named ones, and omit "
            "it only after the unscoped rows are the only ones left")
    elif len(vcenters) > 1:
        raise ValueError("catalog contains multiple vSphere vCenters; provide --vcenter")
    else:
        vcenter = next(iter(vcenters)) if len(vcenters) == 1 else None
    library_items, templates = query_live_artifacts(library, vcenter, args.vault_file)

    def scope_match(image):
        image_scope = image.get("scope") or {}
        if image_scope.get("content_library") != library:
            return False
        recorded = image_scope.get("vcenter")
        if vcenter:
            return recorded == vcenter
        return not recorded
    retired = [image for image in catalog["images"] if image.get("provider") == "vsphere"
               and image.get("status") == "retired" and scope_match(image)]
    stale = []
    for image in catalog["images"]:
        if image.get("provider") != "vsphere" or image.get("status") != "published" or not scope_match(image):
            continue
        artifact_id = image["artifact_id"]
        if image["artifact_type"] == "content_library_ova":
            present = artifact_id.removesuffix(".ova") in library_items
        elif image["artifact_type"] == "content_library_template":
            present = artifact_id in templates
        else:
            raise ValueError(
                "unsupported vSphere artifact type: " + image["artifact_type"])
        if not present:
            stale.append((image, "artifact not found"))
    print(f"vSphere scope: vcenter={vcenter or 'unscoped'}, content_library={library}")
    reconcile(args.catalog, "vsphere", stale, retired, scope_match, library, args.dry_run, args.force)

    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"reconcile-catalog-vsphere: {error}")
