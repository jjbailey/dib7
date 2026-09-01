#!/usr/bin/env python3
# reconcile-catalog-aws.py
# vim: set tabstop=4 shiftwidth=4 expandtab:

"""Mark published AWS catalog entries as retired when their AMI is gone.

AWS is documented in publish-image-catalog.py as additive: nothing should
deregister an AMI out from under a published catalog entry. In practice
something outside this pipeline (an AMI-lifecycle cron job, cost cleanup,
etc.) has been deregistering old AMIs anyway, leaving the catalog claiming
'published' for artifacts that no longer exist. This script is the AWS-side
half of closing that gap; tests/validate.sh only checks catalog shape, never
cloud reality.
"""

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
    """Return the subset of ami_ids that still exist in region.

    describe-images silently omits unknown IDs from its response instead of
    erroring, even when every requested ID is unknown - so a plain set
    difference against the response is enough to find what is gone. IDs are
    batched to stay well under the CLI argument-length limit and so one bad
    batch doesn't fail the whole region's reconciliation.
    """
    live = set()
    for start in range(0, len(ami_ids), AMI_BATCH_SIZE):
        batch = ami_ids[start:start + AMI_BATCH_SIZE]
        result = subprocess.run(
            ["aws", "ec2", "describe-images", "--region", region,
             "--image-ids", *batch, "--output", "json"],
            capture_output=True, text=True, check=True,
        )
        live.update(image["ImageId"] for image in json.loads(result.stdout)["Images"])
    return live


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="report what would be retired without writing the catalog",
    )
    args = parser.parse_args()

    lock_path = args.catalog.with_name(args.catalog.name + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
        if catalog.get("schema_version") != 1 or not isinstance(catalog.get("images"), list):
            raise ValueError("catalog must have schema_version 1 and an images list")

        by_region = defaultdict(list)
        for image in catalog["images"]:
            if image.get("provider") != "aws" or image.get("status") != "published":
                continue
            region = image.get("region")
            if not region:
                print(f"skipping {image.get('logical_name')} {image.get('version')}: "
                      f"no region on catalog entry", file=sys.stderr)
                continue
            by_region[region].append(image)

        retired = []
        for region, images in by_region.items():
            live = live_ami_ids(region, [image["artifact_id"] for image in images])
            retired.extend(image for image in images if image["artifact_id"] not in live)

        if not retired:
            print("no stale AWS catalog entries found")
            return 0

        for image in retired:
            print(f"retiring {image['logical_name']} {image['version']} "
                  f"({image['artifact_id']}, {image['region']}): AMI not found")
            if not args.dry_run:
                image["status"] = "retired"

        if args.dry_run:
            print(f"{len(retired)} entries would be retired (--dry-run, catalog not written)")
            return 0

        catalog["images"].sort(
            key=lambda item: (item["logical_name"], item["provider"], item["artifact_type"], item["version"]))
        catalog["generated_at"] = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        fd, temporary = tempfile.mkstemp(prefix=args.catalog.name + ".", dir=args.catalog.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(catalog, output, indent=2, sort_keys=False)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.chmod(temporary, stat.S_IMODE(os.stat(args.catalog).st_mode))
            os.replace(temporary, args.catalog)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

        print(f"retired {len(retired)} entries in {args.catalog}")
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"reconcile-catalog-aws: {error}")
