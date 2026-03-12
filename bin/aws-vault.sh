#!/bin/bash
# aws-vault.sh
# vim: set tabstop=4 shiftwidth=4 expandtab:

set -e

[ -z "$VAULT" ] && VAULT="vaults/aws.yml"
[ -s "$VAULT" ] && action=edit || action=create

ansible-vault $action --encrypt-vault-id=default $VAULT
