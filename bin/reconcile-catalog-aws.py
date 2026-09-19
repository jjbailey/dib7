#!/usr/bin/env python3
# bin/reconcile-catalog-aws.py
# vim: set tabstop=4 shiftwidth=4 expandtab:



"""Remove AWS catalog entries when their AMIs are gone."""

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from reconcile_catalog_common import read_snapshot, reconcile

AMI_BATCH_SIZE = 100


def live_ami_ids(region, ami_ids, profile=None):
    live = set()
    for start in range(0, len(ami_ids), AMI_BATCH_SIZE):
        command = ["aws", "ec2", "describe-images", "--region", region, "--filters",
                   "Name=image-id,Values=" + ",".join(ami_ids[start:start + AMI_BATCH_SIZE]), "--output", "json"]
        if profile:
            command[4:4] = ["--profile", profile]
        result = subprocess.run(
            command, capture_output=True, text=True, check=True)
        live.update(item["ImageId"]
                    for item in json.loads(result.stdout).get("Images", []))
    return live


def main():
    repo_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path,
                        default=repo_dir / "catalogs/image-catalog.json")
    parser.add_argument("--region")
    parser.add_argument("--profile")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    catalog = read_snapshot(args.catalog)
    grouped = defaultdict(list)
    retired = []
    for image in catalog["images"]:
        if image.get("provider") != "aws" or (args.region and image.get("region") != args.region):
            continue
        if image.get("status") == "retired":
            retired.append(image)
        elif image.get("status") == "published":
            if image.get("region"):
                grouped[image["region"]].append(image)
            else:
                print(
                    f"skipping {image.get('logical_name')} {image.get('version')}: no region", file=sys.stderr)
    stale = []
    for region, images in grouped.items():
        live = live_ami_ids(region, [image["artifact_id"]
                            for image in images], args.profile)
        stale.extend((image, "AMI not found")
                     for image in images if image["artifact_id"] not in live)

    def scope_match(image): return not args.region or image.get(
        "region") == args.region
    print(f"AWS scope: region={args.region or 'all catalog regions'}")
    return reconcile(args.catalog, "aws", stale, retired, scope_match, args.region, args.dry_run, args.force)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError, KeyError) as error:
        raise SystemExit(f"reconcile-catalog-aws: {error}")
