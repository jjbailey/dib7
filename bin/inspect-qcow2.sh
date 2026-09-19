#!/bin/bash
# bin/inspect-qcow2.sh
# vim: set tabstop=4 shiftwidth=4 expandtab:

# a script for examining and modifying virtual machine filesystems

PATH=/usr/bin:/usr/sbin:/usr/local/bin
umask 022

usage()
{
    echo "Usage: $0 -i <image_name>"
    echo "  -i <image_name>: Path to the virtual machine image (qcow2 or vmdk)"
    exit 1
}

# Check if required tools are available
command -v guestfish > /dev/null 2>&1 || {
    echo "Error: guestfish is not installed or not in PATH" >&2
    exit 1
}

while getopts "i:" opt ; do
    case "$opt" in
        i) image_name="$OPTARG" ;;
        *) usage ;;
    esac
done

[ -z "$image_name" ] && usage

set -euo pipefail

# Determine disk format from a recognized extension (case-insensitive).
# Leave an unrecognized filename unchanged; guestfish can inspect it without
# requiring the caller to rename files such as "disk.snapshot".
image_dir="$(dirname -- "$image_name")"
image_base="$(basename -- "$image_name")"
shopt -s nocasematch
if [[ $image_base =~ \.qcow2$ ]] ; then
    disk_format=qcow2
    image_base="${image_base%.*}"
    image_name="$image_dir/$image_base.$disk_format"
elif [[ $image_base =~ \.vmdk$ ]] ; then
    disk_format=vmdk
    image_base="${image_base%.*}"
    image_name="$image_dir/$image_base.$disk_format"
else
    disk_format=qcow2
fi
shopt -u nocasematch

# Check if the image file exists
if [ ! -f "$image_name" ] ; then
    echo "Error: $image_name does not exist" >&2
    exit 1
fi

# Run guestfish to inspect/modify the image
sudo guestfish --rw --network -i -a "$image_name"
