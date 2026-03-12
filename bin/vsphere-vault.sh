#!/bin/bash
# vsphere-vault.sh
# vim: set tabstop=4 shiftwidth=4 expandtab:

set -e

[ -z "$VAULT" ] && VAULT="vaults/vsphere.yml"
[ -s "$VAULT" ] && action=edit || action=create

ansible-vault $action --encrypt-vault-id=default $VAULT
