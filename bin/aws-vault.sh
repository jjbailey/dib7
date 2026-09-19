#!/bin/bash
# bin/aws-vault.sh
# vim: set tabstop=4 shiftwidth=4 expandtab:

set -eu

script_dir="$(CDPATH= builtin cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null && builtin pwd -P)"
project_dir="$(CDPATH= builtin cd -- "$script_dir/.." >/dev/null && builtin pwd -P)"

VAULT="${VAULT:-vaults/aws.yml}"
VENV_BIN="${DIB7_VENV_BIN:-$HOME/.dib7/bin}"
ANSIBLE_VAULT="$VENV_BIN/ansible-vault"

case "$VAULT" in
    /*) ;;
    *) VAULT="$project_dir/$VAULT" ;;
esac

[ -x "$ANSIBLE_VAULT" ] || { echo "missing executable: $ANSIBLE_VAULT" >&2; exit 1; }
[ -s "$VAULT" ] && action=edit || action=create

exec "$ANSIBLE_VAULT" "$action" --encrypt-vault-id=default "$VAULT"
