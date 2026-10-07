#!/usr/bin/env python3
# bin/reconcile_catalog_common.py
# vim: set tabstop=4 shiftwidth=4 expandtab:

"""Shared helpers for reading and writing the image catalog.

Both the publisher (bin/publish-image-catalog.py) and the provider reconcilers
(bin/reconcile-catalog-*.py) write the same file, so the load, lock and
atomic-replace logic lives here rather than in each entry point - a correction
to the write path otherwise has to be made twice.
"""

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

def image_fingerprint(image):
    """Identity of one catalog row, not of its cloud artifact.

    logical_name/artifact_type/artifact_id/version repeats across vCenters and
    across a legacy row that has no scope.vcenter and a newer row that does.
    Matching removal on that tuple deletes the twin that was never checked.
    """
    return json.dumps(image, sort_keys=True, separators=(",", ":"))

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
    # active is the guard's denominator, so a scope that spans several regions
    # or projects dilutes it: a purge confined to one region can stay under the
    # threshold. Callers that care pass a narrower scope (see --region in
    # reconcile-catalog-aws.py).
    active = [image for image in read_snapshot(path)["images"] if image.get(
        "provider") == provider and image.get("status") == "published" and scope_match(image)]
    if stale and active and len(stale) * 2 > len(active) and not force:
        raise ValueError(
            f"refusing to remove {len(stale)} of {len(active)} active {provider} entries in {scope_label}; inspect --dry-run and rerun with --force if intentional")
    # Exact rows only. scope_match stays in the signature because every
    # reconciler uses it to decide which rows to discover; it must not also
    # widen removal to a sibling that shares an artifact id.
    del scope_match
    fingerprints = {image_fingerprint(image) for image, _ in removals}
    lock_path = path.with_name(path.name + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        catalog = load_catalog(path)
        before = len(catalog["images"])
        catalog["images"] = [image for image in catalog["images"] if not (
            image.get("provider") == provider and image_fingerprint(image) in fingerprints)]
        changed = before - len(catalog["images"])
        if changed:
            write_catalog(path, catalog)
        fcntl.flock(lock, fcntl.LOCK_UN)
    print(f"removed {changed} entries in {path}")
    return changed
