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

def authenticated_account(profile=None):
    command = ["aws", "sts", "get-caller-identity", "--query", "Account", "--output", "text"]
    if profile:
        command += ["--profile", profile]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    return result.stdout.strip()

def live_ami_ids(region, ami_ids, profile=None):
    live = set()
    for start in range(0, len(ami_ids), AMI_BATCH_SIZE):
        command = ["aws", "ec2", "describe-images"]
        if profile:
            command += ["--profile", profile]
        command += ["--region", region, "--filters",
                    "Name=image-id,Values=" + ",".join(ami_ids[start:start + AMI_BATCH_SIZE]), "--output", "json"]
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
    parser.add_argument("--project", "--account-id", dest="project",
                        help="only reconcile this AWS account/project")
    parser.add_argument("--profile")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    catalog = read_snapshot(args.catalog)
    projects = {image.get("project") for image in catalog["images"]
                if image.get("provider") == "aws" and image.get("project")}
    if args.project:
        project = str(args.project)
    elif len(projects) == 1:
        project = str(next(iter(projects)))
    elif len(projects) > 1:
        raise ValueError("catalog contains multiple AWS projects; provide --project")
    else:
        project = None

    if project and project.isdigit() and len(project) == 12:
        actual_account = authenticated_account(args.profile)
        if actual_account != project:
            raise ValueError(
                f"authenticated AWS account {actual_account} does not match --project {project}")

    grouped = defaultdict(list)
    retired = []
    for image in catalog["images"]:
        if image.get("provider") != "aws" or (args.region and image.get("region") != args.region):
            continue
        # A missing project is not this account. Skipping it here used to
        # disagree with scope_match, which treated the absence as in-scope and
        # deleted the unscoped row anyway.
        if project and image.get("project") != project:
            continue
        if not image.get("region"):
            print(
                f"skipping {image.get('logical_name')} {image.get('version')}: no region",
                file=sys.stderr)
            continue
        if image.get("status") == "retired":
            retired.append(image)
        elif image.get("status") == "published":
            grouped[image["region"]].append(image)
    stale = []
    for region, images in grouped.items():
        live = live_ami_ids(region, [image["artifact_id"]
                            for image in images], args.profile)
        stale.extend((image, "AMI not found")
                     for image in images if image["artifact_id"] not in live)

    # Without --region this scopes to the whole account, and that same scope is
    # the denominator of the majority guard in reconcile(): a region-wide AMI
    # purge can therefore stay under the "more than half" threshold and be
    # applied without --force. Pass --region to narrow both.
    def scope_match(image):
        if args.region and image.get("region") != args.region:
            return False
        if not image.get("region"):
            return False
        if project and image.get("project") != project:
            return False
        return True
    print(f"AWS scope: project={project or 'legacy/all'}, region={args.region or 'all catalog regions'}")
    return reconcile(args.catalog, "aws", stale, retired, scope_match, project or args.region or "AWS catalog", args.dry_run, args.force)

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError, KeyError) as error:
        raise SystemExit(f"reconcile-catalog-aws: {error}")
