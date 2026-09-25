#!/usr/bin/env python3
# bin/reconcile_catalog_common.py
# vim: set tabstop=4 shiftwidth=4 expandtab:



"""Shared helpers for provider image-catalog reconcilers."""

import datetime as dt
import fcntl
import json
import os
import stat
import tempfile


def now_utc():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_catalog(path):
    if not path.exists():
        raise ValueError(f"no catalog at {path}")
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if catalog.get("schema_version") != 1 or not isinstance(catalog.get("images"), list):
        raise ValueError(
            "catalog must have schema_version 1 and an images list")
    return catalog


def read_snapshot(path):
    lock_path = path.with_name(path.name + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        catalog = load_catalog(path)
        fcntl.flock(lock, fcntl.LOCK_UN)
    return catalog


def image_key(image):
    return (image.get("logical_name"), image.get("artifact_type"), image.get("artifact_id"), image.get("version"))


def write_catalog(path, catalog):
    catalog["images"].sort(key=lambda item: (item.get("logical_name", ""), item.get(
        "provider", ""), item.get("artifact_type", ""), item.get("version", "")))
    catalog["generated_at"] = now_utc()
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


def reconcile(path, provider, stale, retired, scope_match, scope_label, dry_run, force):
    removals = stale + [(image, "already retired") for image in retired]
    if not removals:
        print(f"no stale {provider} catalog entries found")
        return 0
    for image, reason in removals:
        action = "removing" if reason != "already retired" else "removing previously retired"
        print(f"{action} {image.get('logical_name')} {image.get('version')} ({image.get('artifact_id')}): {reason}")
    if dry_run:
        print(
            f"{len(removals)} entries would be removed (--dry-run, catalog not written)")
        return 0
    active = [image for image in read_snapshot(path)["images"] if image.get(
        "provider") == provider and image.get("status") == "published" and scope_match(image)]
    if stale and active and len(stale) * 2 > len(active) and not force:
        raise ValueError(
            f"refusing to remove {len(stale)} of {len(active)} active {provider} entries in {scope_label}; inspect --dry-run and rerun with --force if intentional")
    keys = {image_key(image) for image, _ in removals}
    lock_path = path.with_name(path.name + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        catalog = load_catalog(path)
        before = len(catalog["images"])
        catalog["images"] = [image for image in catalog["images"] if not (image.get(
            "provider") == provider and image_key(image) in keys and scope_match(image))]
        changed = before - len(catalog["images"])
        if changed:
            write_catalog(path, catalog)
        fcntl.flock(lock, fcntl.LOCK_UN)
    print(f"removed {changed} entries in {path}")
    return changed
