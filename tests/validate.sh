#!/bin/bash
# validate.sh
# vim: set tabstop=4 shiftwidth=4 expandtab:

# Without set -e every check below could fail, be ignored, and the script would
# still print "Validation passed." and exit 0 -- which is exactly how this
# suite behaved until it was fixed. Do not remove.
set -euo pipefail

repo_dir="$(CDPATH= builtin cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." > /dev/null && builtin pwd -P)"
cd "$repo_dir"

# CLAUDE.md mandates the patched venv at ~/.dib7/bin/ansible-playbook, not
# whatever ansible-playbook happens to be first on PATH.
venv_bin="${DIB7_VENV_BIN:-$HOME/.dib7/bin}"
ansible_playbook="$venv_bin/ansible-playbook"
python_bin="$venv_bin/python3"

failures=0

fail()
{
    echo "FAIL: $*" >&2
    failures=$((failures + 1))
}

echo "== environment =="
venv_root="${venv_bin%/bin}"
if [ -x "$ansible_playbook" ] && [ -x "$python_bin" ] &&
   "$ansible_playbook" --version 2>/dev/null | grep -q "ansible python module location = $venv_root/"; then
    echo "  ok   venv entry points"
else
    fail "missing venv entry point(s) under $venv_bin"
fi

echo "== collection versions =="
ansible_galaxy="$venv_bin/ansible-galaxy"
if "$python_bin" - "$ansible_galaxy" << 'PYTHON'
import json
import subprocess
import sys
from pathlib import Path
import yaml

requirements = yaml.safe_load(Path("requirements.yml").read_text())
installed = json.loads(subprocess.check_output(
    [sys.argv[1], "collection", "list", "--format", "json"],
    text=True,
    stderr=subprocess.DEVNULL,
))
versions = {}
for location in installed.values():
    for name, metadata in location.items():
        versions[name] = metadata.get("version")
missing = []
for requirement in requirements.get("collections", []):
    name = requirement["name"]
    expected = str(requirement["version"])
    actual = versions.get(name)
    if actual != expected:
        missing.append(f"{name}: expected {expected}, found {actual or 'missing'}")
if missing:
    raise SystemExit("; ".join(missing))
PYTHON
then
    echo "  ok   pinned Ansible collections"
else
    fail "installed Ansible collections do not match requirements.yml"
fi

echo "== Fedora DIB compatibility =="
fedora_element="$($python_bin -c 'import site; print(site.getsitepackages()[0])')/diskimage_builder/elements/fedora/root.d/10-fedora-cloud-image"
if [ -f "$fedora_element" ] && grep -q 'Fedora-Cloud-Base-Generic' "$fedora_element"; then
    echo "  ok   Fedora Generic-image naming is supported"
else
    dib_version="$($python_bin -c 'from importlib.metadata import version; print(version("diskimage-builder"))' 2>/dev/null || echo unknown)"
    fail "diskimage-builder $dib_version lacks Fedora Generic-image support; apply patches/diskimage-builder-fedora-generic-image.patch or upgrade to a release that includes it"
fi

echo "== ansible playbook syntax =="
for playbook in playbooks/*.yml ; do
    # These are tasks files, not playbooks; they are syntax-checked when
    # included by the real playbooks.
    case "$(basename "$playbook")" in
        common-setup.yml | publish-image-catalog.yml | verify-stamp.yml) continue ;;
    esac
    if "$ansible_playbook" -i hosts.yml "$playbook" --syntax-check > /dev/null ; then
        echo "  ok   $playbook"
    else
        fail "$playbook failed --syntax-check"
    fi
done

echo "== shell syntax =="
# bin/, tests/, and local wrappers plus every element hook.
while IFS= read -r script ; do
    if bash -n "$script" ; then
        echo "  ok   $script"
    else
        fail "$script failed bash -n"
    fi
done < <(
    find bin tests local -type f -name '*.sh' 2> /dev/null
    find elements -type f \( \
        -path '*/pre-install.d/*' -o \
        -path '*/install.d/*' -o \
        -path '*/post-install.d/*' -o \
        -path '*/finalise.d/*' -o \
        -path '*/root.d/*' -o \
        -path '*/environment.d/*' -o \
        -path '*/extra-data.d/*' -o \
        -path '*/post-root.d/*' -o \
        -path '*/pre-finalise.d/*' -o \
        -path '*/block-device.d/*' -o \
        -path '*/cleanup.d/*' \
        \) 2> /dev/null
)

echo "== Python syntax =="
while IFS= read -r script ; do
    if "$python_bin" -m py_compile "$script" ; then
        echo "  ok   $script"
    else
        fail "$script failed py_compile"
    fi
done < <(find bin -type f -name "*.py" 2> /dev/null)
rm -rf bin/__pycache__

echo "== catalog schema =="
if "$python_bin" - << 'PYTHON' ; then
import json
from pathlib import Path
from jsonschema import Draft202012Validator
schema = json.loads(Path("catalogs/image-catalog.schema.json").read_text())
validator = Draft202012Validator(schema)
for path in sorted(Path("catalogs").glob("*.json")):
    if path.name == "image-catalog.schema.json":
        continue
    data = json.loads(path.read_text())
    errors = sorted(validator.iter_errors(data), key=lambda error: list(error.path))
    if errors:
        raise SystemExit(f"{path}: {errors[0].message}")
PYTHON
    echo "  ok   catalog JSON matches schema"
else
    fail "catalog schema validation failed"
fi

echo "== powershell syntax =="
if command -v pwsh > /dev/null 2>&1 ; then
    for ps in bin/*.ps1 ; do
        if pwsh -NoProfile -Command "
            \$errs = \$null
            \$tokens = \$null
            [System.Management.Automation.Language.Parser]::ParseFile(
                '$repo_dir/$ps', [ref]\$tokens, [ref]\$errs) | Out-Null
            if (\$errs) { \$errs | ForEach-Object { Write-Host \$_ } ; exit 1 }
        " ; then
            echo "  ok   $ps"
        else
            fail "$ps failed to parse"
        fi
    done
else
    echo "  skip pwsh not installed"
fi

echo "== yaml parse =="
if "$python_bin" - << 'PYTHON' ; then
import sys
from pathlib import Path

import yaml

rc = 0
for path in sorted([*Path('.').glob('**/*.yml'), *Path('.').glob('**/*.yaml')]):
    # Vaults are encrypted; .git may hold sample YAML from hook templates.
    if 'vaults' in path.parts or '.git' in path.parts:
        continue
    try:
        yaml.safe_load(path.read_text())
    except Exception as exc:
        print(f"  {path}: {exc}", file=sys.stderr)
        rc = 1
sys.exit(rc)
PYTHON
    echo "  ok   all yaml parsed"
else
    fail "YAML parse error"
fi

if [ "$failures" -ne 0 ] ; then
    echo "Validation FAILED: $failures problem(s)." >&2
    exit 1
fi

echo "Validation passed."
