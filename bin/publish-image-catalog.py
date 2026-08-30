#!/usr/bin/env python3
# publish-image-catalog.py
# vim: set tabstop=4 shiftwidth=4 expandtab:

"""Atomically merge one published image into the DIB7 image catalog."""

import argparse
import datetime as dt
import fcntl
import json
import os
import pathlib
import stat
import tempfile


REQUIRED = {
    "logical_name", "provider", "artifact_id", "artifact_type", "version",
    "architecture", "boot_mode", "source_build", "status",
}
PROVIDERS = {"aws", "gcp", "openstack", "vsphere"}
STATUSES = {"published", "retired"}


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
        if path.exists():
            catalog = json.loads(path.read_text(encoding="utf-8"))
        else:
            catalog = {"schema_version": 1, "images": []}
        if catalog.get("schema_version") != 1 or not isinstance(catalog.get("images"), list):
            raise ValueError("catalog must have schema_version 1 and an images list")

        # artifact_type is part of the identity so one image can be published as
        # more than one kind of artifact per provider per run - a vSphere OVA
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
        # Rows for other providers are never examined, so a publisher only ever
        # rewrites its own provider's slice of the catalog.
        if args.supersede:
            key = (entry["logical_name"], entry["provider"], entry["artifact_type"])
            match = lambda old: (old.get("logical_name"), old.get("provider"), old.get("artifact_type"))
        else:
            key = (entry["logical_name"], entry["provider"], entry["artifact_type"], entry["version"])
            match = lambda old: (old.get("logical_name"), old.get("provider"), old.get("artifact_type"), old.get("version"))
        catalog["images"] = [old for old in catalog["images"] if match(old) != key]
        catalog["images"].append(entry)
        catalog["images"].sort(key=lambda item: (item["logical_name"], item["provider"], item["artifact_type"], item["version"]))
        catalog["generated_at"] = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(catalog, output, indent=2, sort_keys=False)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            try:
                mode = stat.S_IMODE(os.stat(path).st_mode)
            except FileNotFoundError:
                mode = 0o644
            os.chmod(temporary, mode)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"publish-image-catalog: {error}")
