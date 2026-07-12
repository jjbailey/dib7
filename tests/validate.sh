#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(CDPATH= builtin cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." >/dev/null && builtin pwd -P)"
cd "$repo_dir"

for playbook in playbooks/*.yml; do
    [ "$(basename "$playbook")" = "common-setup.yml" ] && continue
    ansible-playbook -i hosts.yml "$playbook" --syntax-check >/dev/null
done

for script in bin/*.sh; do
    bash -n "$script"
done

python3 - <<'PYTHON'
from pathlib import Path
import yaml

for path in [*Path('.').glob('**/*.yml'), *Path('.').glob('**/*.yaml')]:
    if 'vaults' in path.parts:
        continue
    yaml.safe_load(path.read_text())
PYTHON

echo "Validation passed."
