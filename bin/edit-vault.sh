#!/bin/bash
# bin/edit-vault.sh
# vim: set tabstop=4 shiftwidth=4 expandtab:

# Edit (or create) one encrypted vault file.
#
# The per-target entry points -- aws-vault.sh, gcp-vault.sh,
# openstack-vault.sh, vsphere-vault.sh -- are symlinks to this
# script; the name it was invoked as selects vaults/<target>.yml. Set VAULT to
# edit some other file.

set -eu

script_dir="$(CDPATH= builtin cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null && builtin pwd -P)"
project_dir="$(CDPATH= builtin cd -- "$script_dir/.." >/dev/null && builtin pwd -P)"

invoked_as="$(basename -- "$0")"
target="${invoked_as%-vault.sh}"
if [ "$target" = "$invoked_as" ] || [ -z "$target" ] ; then
    if [ -z "${VAULT:-}" ] ; then
        echo "$invoked_as: run this through <target>-vault.sh, or set VAULT" >&2
        exit 2
    fi
    target=""
fi

VAULT="${VAULT:-vaults/$target.yml}"
VENV_BIN="${DIB7_VENV_BIN:-$HOME/.dib7/bin}"
ANSIBLE_VAULT="$VENV_BIN/ansible-vault"

case "$VAULT" in
    /*) ;;
    *) VAULT="$project_dir/$VAULT" ;;
esac

[ -x "$ANSIBLE_VAULT" ] || { echo "missing executable: $ANSIBLE_VAULT" >&2; exit 1; }
[ -s "$VAULT" ] && action=edit || action=create

exec "$ANSIBLE_VAULT" "$action" --encrypt-vault-id=default "$VAULT"
