#!/usr/bin/env python3
# reconcile-catalog-aws.py
# vim: set tabstop=4 shiftwidth=4 expandtab:

"""Mark published AWS catalog entries as retired when their AMI is gone."""

import argparse
import datetime as dt
import fcntl
import json
import os
import stat
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path


AMI_BATCH_SIZE = 100


def live_ami_ids(region, ami_ids):
    """Return the subset of AMI IDs that still exist in a region."""
    live = set()
    for start in range(0, len(ami_ids), AMI_BATCH_SIZE):
        batch = ami_ids[start:start + AMI_BATCH_SIZE]
        result = subprocess.run(
            ["aws", "ec2", "describe-images", "--region", region,
             "--filters", "Name=image-id,Values=" + ",".join(batch),
             "--output", "json"],
            capture_output=True, text=True, check=True,
        )
        live.update(image["ImageId"]
                    for image in json.loads(result.stdout)["Images"])
    return live


def load_catalog(path):
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if catalog.get("schema_version") != 1 or not isinstance(catalog.get("images"), list):
        raise ValueError(
            "catalog must have schema_version 1 and an images list")
    return catalog


def write_catalog(path, catalog):
    catalog["images"].sort(
        key=lambda item: (item.get("logical_name", ""), item.get("provider", ""), item.get("artifact_type", ""), item.get("version", "")))
    catalog["generated_at"] = dt.datetime.now(dt.timezone.utc).replace(
        microsecond=0).isoformat().replace("+00:00", "Z")
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(catalog, output, indent=2, sort_keys=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, stat.S_IMODE(os.stat(path).st_mode))
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="report what would be retired without writing the catalog",
    )
    args = parser.parse_args()
    lock_path = args.catalog.with_name(args.catalog.name + ".lock")

    # Read a consistent snapshot, then release the lock before making network
    # calls. The catalog is re-read under lock before writing so a concurrent
    # publisher is never blocked by AWS latency and cannot be overwritten.
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        catalog = load_catalog(args.catalog)
        fcntl.flock(lock, fcntl.LOCK_UN)

    by_region = defaultdict(list)
    for image in catalog["images"]:
        if image.get("provider") != "aws" or image.get("status") != "published":
            continue
        region = image.get("region")
        if not region:
            print(
                f"skipping {image.get('logical_name')} {image.get('version')}: no region on catalog entry", file=sys.stderr)
            continue
        by_region[region].append(image)

    retired = []
    for region, images in by_region.items():
        live = live_ami_ids(region, [image["artifact_id"] for image in images])
        retired.extend(
            image for image in images if image["artifact_id"] not in live)

    if not retired:
        print("no stale AWS catalog entries found")
        return 0

    for image in retired:
        print(
            f"retiring {image['logical_name']} {image['version']} ({image['artifact_id']}, {image['region']}): AMI not found")
    if args.dry_run:
        print(
            f"{len(retired)} entries would be retired (--dry-run, catalog not written)")
        return 0

    retired_keys = {
        (image["logical_name"], image["artifact_type"],
         image["artifact_id"], image["version"])
        for image in retired
    }
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        catalog = load_catalog(args.catalog)
        changed = 0
        for image in catalog["images"]:
            key = (image.get("logical_name"), image.get("artifact_type"),
                   image.get("artifact_id"), image.get("version"))
            if key in retired_keys and image.get("provider") == "aws" and image.get("status") == "published":
                image["status"] = "retired"
                changed += 1
        if changed:
            write_catalog(args.catalog, catalog)
        fcntl.flock(lock, fcntl.LOCK_UN)

    print(f"retired {changed} entries in {args.catalog}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError, KeyError) as error:
        raise SystemExit(f"reconcile-catalog-aws: {error}")
