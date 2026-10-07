#!/usr/bin/env python3
# bin/publish-image-catalog.py
# vim: set tabstop=4 shiftwidth=4 expandtab:

"""Atomically merge one published image into the DIB7 image catalog."""

import argparse
import fcntl
import json
import pathlib

from reconcile_catalog_common import load_catalog, write_catalog

REQUIRED = {
    "logical_name", "provider", "artifact_id", "artifact_type", "version",
    "architecture", "boot_mode", "source_build", "status",
}
PROVIDERS = {"aws", "gcp", "openstack", "vsphere"}
STATUSES = {"published", "retired"}

def scope_identity(entry):
    """Return the provider scope that must remain distinct in the catalog."""
    return (entry.get("project"), entry.get("region"),
            json.dumps(entry.get("scope") or {}, sort_keys=True,
                       separators=(",", ":")))

def validate(entry):
    missing = sorted(REQUIRED - entry.keys())
    if missing:
        raise ValueError("catalog entry missing: " + ", ".join(missing))
    if entry["provider"] not in PROVIDERS:
        raise ValueError("unsupported provider: " + str(entry["provider"]))
    if entry["status"] not in STATUSES:
        raise ValueError("unsupported status: " + str(entry["status"]))
    for name in REQUIRED:
        if not isinstance(entry[name], str) or not entry[name].strip():
            raise ValueError(name + " must be a non-empty string")
    if "ssh_username" in entry and (
            not isinstance(entry["ssh_username"], str) or
            not entry["ssh_username"].strip()):
        raise ValueError("ssh_username must be a non-empty string")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--entry", required=True, type=pathlib.Path)
    parser.add_argument(
        "--supersede",
        action="store_true",
        help="drop older versions of this logical_name/provider/artifact_type "
             "instead of keeping them alongside. For providers where a new run "
             "destroys or overwrites what the older rows point at: gcp, "
             "openstack and vsphere, but not aws.",
    )
    args = parser.parse_args()

    entry = json.loads(args.entry.read_text(encoding="utf-8"))
    validate(entry)
    path = pathlib.Path(args.catalog)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        # load_catalog enforces schema_version 1 and an images list. Only the
        # missing-file case is ours: a first publish legitimately starts from an
        # empty catalog.
        if path.exists():
            catalog = load_catalog(path)
        else:
            catalog = {"schema_version": 1, "images": []}

        # artifact_type and provider scope are part of the identity so one image
        # can be published as multiple artifact kinds and targets - a vSphere OVA
        # and the template built from it, an AMI and a snapshot. Without it the
        # second publisher silently evicts the first.
        #
        # --supersede drops version from the comparison, so the new entry
        # replaces every version of the same artifact rather than joining them.
        # The test is whether a new run destroys what the older rows point at,
        # not whether the artifact id looks unique:
        #   vsphere   - library item and template are named for the image, so a
        #               run overwrites them in place
        #   gcp       - image is deleted and recreated under the same name, so
        #               the selfLink is stable and its content changes
        #   openstack - image is deleted by name, so the old UUID stops
        #               resolving even though each upload mints a new one
        #   aws       - nothing is deregistered and each import mints a new AMI
        #               id, so older versions stay independently deployable
        # Only AWS is additive; the other three supersede.
        #
        # Rows for other providers or other project/region/scope slices are never
        # examined, so a publisher only rewrites its own target slice.
        if args.supersede:
            key = (entry["logical_name"], entry["provider"],
                   entry["artifact_type"], *scope_identity(entry))

            def match(old): return (old.get("logical_name"),
                                    old.get("provider"), old.get("artifact_type"),
                                    *scope_identity(old))
        else:
            key = (entry["logical_name"], entry["provider"],
                   entry["artifact_type"], entry["version"], *scope_identity(entry))

            def match(old): return (old.get("logical_name"), old.get(
                "provider"), old.get("artifact_type"), old.get("version"),
                *scope_identity(old))
        catalog["images"] = [
            old for old in catalog["images"] if match(old) != key]
        catalog["images"].append(entry)
        # Sorts, stamps generated_at, and replaces the file atomically. Shared
        # with the provider reconcilers so the two writers cannot drift.
        write_catalog(path, catalog)

if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, json.JSONDecodeError, KeyError) as error:
        raise SystemExit(f"publish-image-catalog: {error}")
