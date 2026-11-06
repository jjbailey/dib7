#!/usr/bin/env python3
# bin/reconcile-catalog-aws.py
# vim: set tabstop=4 shiftwidth=4 expandtab:

"""Remove AWS catalog entries when their AMIs are gone."""

import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from reconcile_catalog_common import (
    read_snapshot,
    read_vault,
    reconcile,
    report_credentials,
    select_vault_project,
    vault_projects,
)

AMI_BATCH_SIZE = 100
DEAD_AMI_STATES = frozenset({"failed", "error", "invalid"})

# Exported variables that pick AWS credentials on purpose; the aws CLI reads them.
AWS_ENVIRONMENT = ("AWS_PROFILE", "AWS_ACCESS_KEY_ID", "AWS_WEB_IDENTITY_TOKEN_FILE")

class AwsCredentials:
    """How to run the aws CLI: an optional --profile and environment overrides."""

    def __init__(self, profile=None, env=None):
        self.profile = profile
        self.env = env

def aws_credentials(project, vault_file, profile=None):
    """--profile, then AWS_* environment, then the vault, then the CLI's chain.

    The vault entry is the aws_projects one whose key or aws_account_id is
    the reconciled account (AWS_TARGET_PROJECT disambiguates, as for the
    import playbooks). It may name an aws_profile or carry access keys,
    which are handed to the CLI through its environment. Without one, the
    CLI's remaining chain (the default ~/.aws profile, an instance profile)
    applies.
    """
    if profile:
        report_credentials("AWS", f"--profile {profile}")
        return AwsCredentials(profile=profile)
    exported = [name for name in AWS_ENVIRONMENT if os.environ.get(name, "").strip()]
    if exported:
        report_credentials("AWS", f"{exported[0]} environment")
        return AwsCredentials()
    document = read_vault(vault_file)
    if document is not None:
        legacy = (document if str(document.get("aws_region") or "").strip()
                  and "s3_bucket" in document and "vmimport_role_name" in document else None)
        legacy_account = str((legacy or {}).get("aws_account_id")
                             or (legacy or {}).get("account_id") or "").strip()
        if legacy and not os.environ.get("AWS_TARGET_PROJECT", "").strip() and (
                not project or not legacy_account or legacy_account == project):
            selected = ("legacy", legacy)
        else:
            selected = select_vault_project(
                vault_projects(document, "aws_projects"), project,
                ("aws_account_id", "account_id", "aws_profile", "profile"),
                "AWS_TARGET_PROJECT", "aws_projects")
        if selected is not None:
            key, entry = selected
            source = (f"{Path(vault_file).name} legacy" if entry is legacy
                      else f"{Path(vault_file).name} aws_projects[{key}]")
            entry_profile = str(entry.get("aws_profile") or entry.get("profile") or "").strip()
            if entry_profile:
                report_credentials("AWS", f"{source} (profile {entry_profile})")
                return AwsCredentials(profile=entry_profile)
            key_id = str(entry.get("aws_access_key_id") or "").strip()
            secret = str(entry.get("aws_secret_access_key") or "").strip()
            if not (key_id and secret):
                raise ValueError(
                    f"{source} has neither aws_profile nor "
                    "aws_access_key_id/aws_secret_access_key")
            # The CLI's own credential variables: they sit in the child's
            # environment (same-user /proc only), never on a command line.
            env = dict(os.environ, AWS_ACCESS_KEY_ID=key_id, AWS_SECRET_ACCESS_KEY=secret)
            token = str(entry.get("aws_session_token") or "").strip()
            if token:
                env["AWS_SESSION_TOKEN"] = token
            else:
                env.pop("AWS_SESSION_TOKEN", None)
            report_credentials("AWS", source)
            return AwsCredentials(env=env)
    report_credentials("AWS", "aws CLI default chain (~/.aws, instance profile)")
    return AwsCredentials()

def _aws(command, credentials):
    if credentials is not None and credentials.profile:
        command = command + ["--profile", credentials.profile]
    env = credentials.env if credentials is not None else None
    return subprocess.run(command, capture_output=True, text=True, check=True, env=env)

def authenticated_account(credentials=None):
    result = _aws(["aws", "sts", "get-caller-identity", "--query", "Account", "--output", "text"],
                  credentials)
    return result.stdout.strip()

def live_ami_ids(region, ami_ids, credentials=None):
    live = set()
    for start in range(0, len(ami_ids), AMI_BATCH_SIZE):
        command = ["aws", "ec2", "describe-images", "--region", region, "--filters",
                   "Name=image-id,Values=" + ",".join(ami_ids[start:start + AMI_BATCH_SIZE]),
                   "--output", "json"]
        result = _aws(command, credentials)
        # A failed/error/invalid AMI is not bootable, so its row goes too.
        # Anything else, including 'pending' from an import still finishing,
        # stays: dropping it would race a concurrent publish.
        live.update(item["ImageId"]
                    for item in json.loads(result.stdout).get("Images", [])
                    if item.get("State") not in DEAD_AMI_STATES)
    return live

def main():
    repo_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path,
                        default=repo_dir / "catalogs/image-catalog.json")
    parser.add_argument("--region")
    parser.add_argument("--project", "--account-id", dest="project",
                        help="only reconcile this AWS account/project")
    parser.add_argument("--profile", help="aws CLI profile, instead of AWS_* or the vault")
    parser.add_argument("--vault-file", type=Path, default=repo_dir / "vaults/aws.yml",
                        help="encrypted vault holding aws_projects credentials")
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

    resolved = {}
    def credentials():
        # Resolved on first use, so a run with nothing to look up never
        # touches the vault or the CLI.
        if "credentials" not in resolved:
            resolved["credentials"] = aws_credentials(project, args.vault_file, args.profile)
        return resolved["credentials"]

    if project and project.isdigit() and len(project) == 12:
        actual_account = authenticated_account(credentials())
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
                            for image in images], credentials())
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
    reconcile(args.catalog, "aws", stale, retired, scope_match, project or args.region or "AWS catalog", args.dry_run, args.force)

    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError, KeyError) as error:
        raise SystemExit(f"reconcile-catalog-aws: {error}")
