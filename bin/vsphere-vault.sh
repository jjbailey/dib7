#!/bin/bash
# vsphere-vault.sh
# vim: set tabstop=4 shiftwidth=4 expandtab:

set -e

script_dir="$(CDPATH= builtin cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null && builtin pwd -P)"
project_dir="$(CDPATH= builtin cd -- "$script_dir/.." >/dev/null && builtin pwd -P)"

[ -z "$VAULT" ] && VAULT="vaults/vsphere.yml"

case "$VAULT" in
    /*) ;;
    *) VAULT="$project_dir/$VAULT" ;;
esac

[ -s "$VAULT" ] && action=edit || action=create

ansible-vault $action --encrypt-vault-id=default $VAULT
