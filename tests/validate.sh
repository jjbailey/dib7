#!/bin/bash
# validate.sh
# vim: set tabstop=4 shiftwidth=4 expandtab:

# Without set -e every check below could fail, be ignored, and the script would
# still print "Validation passed." and exit 0 -- which is exactly how this
# suite behaved until it was fixed. Do not remove.
set -euo pipefail

repo_dir="$(CDPATH= builtin cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." >/dev/null && builtin pwd -P)"
cd "$repo_dir"

failures=0

fail()
{
    echo "FAIL: $*" >&2
    failures=$((failures + 1))
}

echo "== ansible playbook syntax =="
for playbook in playbooks/*.yml ; do
    # These are tasks files, not playbooks; they are syntax-checked when
    # included by the real playbooks.
    case "$(basename "$playbook")" in
        common-setup.yml|verify-stamp.yml) continue ;;
    esac
    if ansible-playbook -i hosts.yml "$playbook" --syntax-check > /dev/null ; then
        echo "  ok   $playbook"
    else
        fail "$playbook failed --syntax-check"
    fi
done

echo "== shell syntax =="
# bin/, local/ and tests/ helpers plus every element hook, which is where most
# of the shell in this repo actually lives.
while IFS= read -r script ; do
    if bash -n "$script" ; then
        echo "  ok   $script"
    else
        fail "$script failed bash -n"
    fi
done < <(
    find bin local tests -type f -name '*.sh' 2> /dev/null
    find elements -type f \( \
        -path '*/pre-install.d/*' -o \
        -path '*/install.d/*' -o \
        -path '*/post-install.d/*' -o \
        -path '*/finalise.d/*' -o \
        -path '*/root.d/*' -o \
        -path '*/environment.d/*' \
        \) 2> /dev/null
)

echo "== powershell syntax =="
if command -v pwsh > /dev/null 2>&1 ; then
    for ps in bin/*.ps1 ; do
        if pwsh -NoProfile -Command "
            \$errs = \$null
            \$tokens = \$null
            [System.Management.Automation.Language.Parser]::ParseFile(
                '$repo_dir/$ps', [ref]\$tokens, [ref]\$errs) | Out-Null
            if (\$errs) { \$errs | ForEach-Object { Write-Host \$_ }; exit 1 }
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
if python3 - << 'PYTHON' ; then
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
