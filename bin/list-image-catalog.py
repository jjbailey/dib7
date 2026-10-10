#!/usr/bin/env python3
# bin/list-image-catalog.py
# vim: set tabstop=4 shiftwidth=4 expandtab:

"""Print a read-only, filterable report of published DIB7 images."""

from __future__ import annotations

import argparse
import json
import shutil
import textwrap
from pathlib import Path
from typing import Any

from reconcile_catalog_common import load_catalog

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CATALOG = REPO_ROOT / "catalogs" / "image-catalog.json"
PROVIDERS = ("aws", "gcp", "openstack", "vsphere")

def _parse_scope(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("scope filters must use KEY=VALUE")
    key, expected = value.split("=", 1)
    if not key or not expected:
        raise argparse.ArgumentTypeError("scope filters must use non-empty KEY=VALUE")
    return key, expected

def _matches(entry: dict[str, Any], args: argparse.Namespace) -> bool:
    if args.status != "all" and entry.get("status") != args.status:
        return False
    if args.provider and entry.get("provider") != args.provider:
        return False
    if args.logical_name and entry.get("logical_name") != args.logical_name:
        return False
    if args.artifact_type and entry.get("artifact_type") != args.artifact_type:
        return False
    if args.project and entry.get("project") != args.project:
        return False
    if args.region and entry.get("region") != args.region:
        return False
    scope = entry.get("scope") or {}
    return all(scope.get(key) == expected for key, expected in args.scope)

def _scope_text(scope: Any) -> str:
    if not isinstance(scope, dict) or not scope:
        return "-"
    return ", ".join(f"{key}={value}" for key, value in sorted(scope.items()))

def _print_field(label: str, value: Any, width: int) -> None:
    prefix = f"  {label:<14} "
    text = "-" if value is None or value == "" else str(value)
    lines = textwrap.wrap(
        text,
        width=max(20, width - len(prefix)),
        break_long_words=True,
        break_on_hyphens=False,
    ) or [""]
    print(prefix + lines[0])
    for line in lines[1:]:
        print(" " * len(prefix) + line)

def _sort_key(entry: dict[str, Any]) -> tuple[str, ...]:
    scope = entry.get("scope") or {}
    return (
        str(entry.get("logical_name", "")),
        str(entry.get("provider", "")),
        str(entry.get("artifact_type", "")),
        str(entry.get("project", "")),
        str(entry.get("region", "")),
        json.dumps(scope, sort_keys=True),
    )

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Browse published entries in the DIB7 image catalog."
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=DEFAULT_CATALOG,
        help="catalog JSON file (default: catalogs/image-catalog.json)",
    )
    parser.add_argument("--provider", choices=PROVIDERS, help="filter by provider")
    parser.add_argument(
        "--image",
        "--logical-name",
        dest="logical_name",
        help="filter by exact logical image name",
    )
    parser.add_argument("--artifact-type", help="filter by exact artifact type")
    parser.add_argument("--project", help="filter by exact project")
    parser.add_argument("--region", help="filter by exact region")
    parser.add_argument(
        "--scope",
        action="append",
        type=_parse_scope,
        default=[],
        metavar="KEY=VALUE",
        help="filter by a scope field; may be repeated",
    )
    parser.add_argument(
        "--status",
        choices=("published", "retired", "all"),
        default="published",
        help="entries to show (default: published)",
    )
    args = parser.parse_args(argv)

    try:
        catalog = load_catalog(args.catalog)
    except (OSError, ValueError) as error:
        raise SystemExit(f"list-image-catalog: {error}") from error

    images = catalog["images"]
    if any(not isinstance(entry, dict) for entry in images):
        raise SystemExit("list-image-catalog: every catalog image must be an object")

    matches = [entry for entry in images if _matches(entry, args)]
    matches.sort(key=lambda entry: str(entry.get("version", "")), reverse=True)
    matches.sort(key=_sort_key)

    source = (
        "catalogs/image-catalog.json"
        if args.catalog.resolve() == DEFAULT_CATALOG.resolve()
        else str(args.catalog)
    )
    print(f"Image catalog: {source}")
    print(f"Entries: {len(matches)} ({args.status})")
    filters = []
    for label, value in (
        ("provider", args.provider),
        ("image", args.logical_name),
        ("artifact type", args.artifact_type),
        ("project", args.project),
        ("region", args.region),
    ):
        if value:
            filters.append(f"{label}={value}")
    filters.extend(f"scope.{key}={value}" for key, value in args.scope)
    if filters:
        print("Filters: " + "; ".join(filters))
    if not matches:
        print("No matching catalog entries.")
        return 0

    width = max(72, shutil.get_terminal_size(fallback=(100, 20)).columns)
    for index, entry in enumerate(matches):
        if index:
            print()
        print(
            f"{entry.get('logical_name', '<unnamed>')} "
            f"[{entry.get('provider', '?')} / {entry.get('artifact_type', '?')}]"
        )
        _print_field("Status", entry.get("status"), width)
        _print_field("Version", entry.get("version"), width)
        _print_field("Project", entry.get("project"), width)
        _print_field("Region", entry.get("region"), width)
        _print_field("Scope", _scope_text(entry.get("scope")), width)
        _print_field("Artifact ID", entry.get("artifact_id"), width)
        _print_field("Architecture", entry.get("architecture"), width)
        _print_field("Boot mode", entry.get("boot_mode"), width)
        _print_field("SSH username", entry.get("ssh_username"), width)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
