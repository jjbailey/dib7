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
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

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

# Credentials. The reconcilers take them in the usual order: an explicit
# command-line flag, then credential variables exported in the environment,
# then the provider's vault entry for the reconciled scope, then whatever the
# SDK or CLI finds on its own (az login, ~/.aws, gcloud). Exported variables
# are a deliberate per-shell choice, so they win; cached logins are often
# stale or blocked, so they come last. The vault is opened only when it is
# needed and never with a prompt.

def _vault_password_file():
    """Use the same lookup as bin/edit-vault.sh, minus the prompt."""
    configured = os.environ.get("VAULT_PASSWORD_FILE")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_file():
            raise ValueError(f"VAULT_PASSWORD_FILE does not name a readable file: {path}")
        return path
    default = Path.home() / ".ssh" / "dib-vault-pass"
    return default if default.is_file() else None

def _ansible_vault_binary():
    venv_binary = Path(os.environ.get("DIB7_VENV_BIN", str(Path.home() / ".dib7" / "bin"))) / "ansible-vault"
    if venv_binary.is_file() and os.access(venv_binary, os.X_OK):
        return str(venv_binary)
    return shutil.which("ansible-vault")

def read_vault(vault_file):
    """Return the decrypted vault document.

    Returns None when the vault cannot be opened without prompting (no file,
    no password file, or no ansible-vault), so the caller can fall back. A
    vault that is there but will not decrypt is an error, not a fallback.
    """
    vault_file = Path(vault_file)
    if not vault_file.is_file():
        return None
    password_file = _vault_password_file()
    binary = _ansible_vault_binary()
    if password_file is None or binary is None:
        return None
    try:
        result = subprocess.run(
            [binary, "view", "--vault-password-file", str(password_file), str(vault_file)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        raise ValueError(
            f"ansible-vault could not decrypt {vault_file} (exit status {error.returncode})"
        ) from error
    import yaml

    document = yaml.safe_load(result.stdout)
    return document if isinstance(document, dict) else {}

def vault_projects(document, map_name):
    """The <map_name> entries of a decrypted vault, keyed by string."""
    projects = (document or {}).get(map_name) or {}
    if not isinstance(projects, dict):
        raise ValueError(f"vault {map_name} is not a mapping")
    return {str(key): entry for key, entry in projects.items() if isinstance(entry, dict)}

def select_vault_project(projects, scope, fields, target_variable, map_name):
    """Pick the vault entry for the reconciled scope, as select-*-project.yml do.

    An explicit request in target_variable (the same *_TARGET_PROJECT the
    import playbooks take) matches a vault key or one of fields. Without one,
    the entry whose fields name the scope is used. Returns (key, entry), or
    None when the vault has no entry for the scope. scope may be None (rows
    that predate a project column); then only an explicit request selects.
    """
    def identities(entry):
        return {str(entry.get(field) or "").strip().lower() for field in fields} - {""}

    scope_id = str(scope).strip().lower() if scope else None
    requested = os.environ.get(target_variable, "").strip() or None
    if requested:
        matches = [(key, entry) for key, entry in projects.items()
                   if requested.lower() in identities(entry) | {key.lower()}]
        if not matches:
            raise ValueError(
                f"{target_variable} {requested!r} matches no key or {'/'.join(fields)} in "
                f"{map_name}; available: {', '.join(sorted(projects)) or '<none>'}")
    elif scope_id:
        matches = [(key, entry) for key, entry in projects.items()
                   if scope_id in identities(entry) | {key.lower()}]
        if not matches:
            return None
    else:
        return None
    if len(matches) > 1:
        raise ValueError(
            f"several {map_name} entries match ({', '.join(sorted(key for key, _ in matches))}); "
            f"set {target_variable} to one key")
    key, entry = matches[0]
    if scope_id and scope_id not in identities(entry) | {key.lower()}:
        named = ", ".join(sorted(identities(entry))) or key
        raise ValueError(f"{map_name}[{key!r}] is for {named}, not {scope}")
    return key, entry

def require_fields(map_name, key, entry, fields):
    for field in fields:
        if not str(entry.get(field) or "").strip():
            raise ValueError(f"{map_name}[{key!r}].{field} must be a non-empty string")

def report_credentials(provider, source):
    print(f"{provider} credentials: {source}", file=sys.stderr)
