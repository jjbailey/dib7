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
from reconcile_catalog_common import read_snapshot, reconcile

POWERSHELL_QUERY = r"""
$ErrorActionPreference = 'Stop'
$password = ConvertTo-SecureString $env:vcenter_password -AsPlainText -Force
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


def query_live_artifacts(library):
    required = ("vcenter_hostname", "vcenter_username", "vcenter_password")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise ValueError(
            "missing vCenter environment variable(s): " + ", ".join(missing))
    env = os.environ.copy()
    env["vsphere_catalog_library"] = library
    result = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-Command", POWERSHELL_QUERY],
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
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    catalog = read_snapshot(args.catalog)
    libraries = {image.get("scope", {}).get("content_library") for image in catalog["images"]
                 if image.get("provider") == "vsphere" and image.get("scope", {}).get("content_library")}
    if not libraries:
        print("no vSphere catalog entries found")
        return 0
    library = args.library or (
        next(iter(libraries)) if len(libraries) == 1 else None)
    if not library:
        raise ValueError(
            "catalog contains multiple vSphere content libraries; provide --library")
    library_items, templates = query_live_artifacts(library)

    def scope_match(image):
        return image.get("scope", {}).get("content_library") == library
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
    print(f"vSphere scope: content_library={library}")
    return reconcile(args.catalog, "vsphere", stale, retired, scope_match, library, args.dry_run, args.force)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"reconcile-catalog-vsphere: {error}")
