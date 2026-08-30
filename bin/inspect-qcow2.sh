#!/bin/bash
# inspect-qcow2.sh
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

# Determine disk format from extension (case-insensitive)
if [[ $image_name =~ \.qcow2$ ]] ; then
    disk_format=qcow2
elif [[ $image_name =~ \.vmdk$ ]] ; then
    disk_format=vmdk
else
    disk_format=qcow2 # Default to qcow2 if no extension
fi

# Normalize image name: remove any existing extension and add the determined
# format. Extension stripping is done on the basename only - "${var%.*}" on
# the full path would strip at the last dot anywhere in the path, mangling a
# dotted directory component (e.g. "./v1.2/img") when the basename itself has
# no extension.
image_dir="$(dirname -- "$image_name")"
image_base="$(basename -- "$image_name")"
image_name="$image_dir/${image_base%.*}.$disk_format"

# Check if the image file exists
if [ ! -f "$image_name" ] ; then
    echo "Error: $image_name does not exist" >&2
    exit 1
fi

# Run guestfish to inspect/modify the image
sudo guestfish --rw --network -i -a "$image_name"
