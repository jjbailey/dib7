#!/bin/bash
# bin/cleanup-dib-build.sh
# vim: set tabstop=4 shiftwidth=4 expandtab:

set -euo pipefail

dry_run=0
case "${1:-}" in
    "") ;;
    --dry-run) dry_run=1 ;;
    -h|--help)
        echo 'Usage: cleanup-dib-build.sh [--dry-run]'
        echo 'Requires DIB_BUILD_DIR; accepts DIB_TMP_DIR and DIB_VG_NAME.'
        exit 0
        ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
esac

build_dir="${DIB_BUILD_DIR:?DIB_BUILD_DIR is required}"
dib_tmp="${DIB_TMP_DIR:-${TMPDIR:-/tmp}/dib_}"
dib_tmp_root="${dib_tmp%/dib_}"
if [ "$dib_tmp_root" = "$dib_tmp" ] ; then
    dib_tmp_root="$(dirname -- "$dib_tmp")"
fi
vg_name="${DIB_VG_NAME:-vg1}"

run()
{
    if ((dry_run)); then
        printf '+ '
        printf '%q ' "$@"
        printf '\n'
    else
        "$@"
    fi
}

run_best_effort()
{
    if ((dry_run)); then
        run "$@"
    else
        "$@" || true
    fi
}

# The bracket expression prevents pgrep from matching this script's command
# line. Refuse to touch shared state while another image build runs.
other_build="$(pgrep -f '(bin|lib)/disk-image[-]create' | tr '\n' ' ' || true)"
if [ -n "$other_build" ]; then
    echo "another image build is already running (pids: $other_build)" >&2
    echo "refusing to tear down shared state underneath it" >&2
    exit 1
fi

mount_points="$(mount | awk -v root="$build_dir" -v tmp="$dib_tmp" '
  { mp = $3 }
  index(mp, root) == 1 && (length(mp) == length(root) || substr(mp, length(root) + 1, 1) == "/") { print length(mp), mp; next }
  index(mp, tmp) == 1 { print length(mp), mp }
' | sort -rn | cut -d" " -f2-)"
while IFS= read -r mount_point; do
    [ -z "$mount_point" ] || run umount -l "$mount_point"
done <<< "$mount_points"

run_best_effort find "$dib_tmp_root" -maxdepth 1 -type d \
    \( -name 'dib_build.*' -o -name 'dib_image.*' \) -exec rm -rf {} +

lvm_loop_devices=""
for vg in $(vgs --noheadings -o vg_name 2>/dev/null | tr -d ' ' || true); do
    [ "$vg" = "$vg_name" ] || continue
    pv_list="$(pvs --noheadings -o pv_name --select "vg_name=$vg" 2>/dev/null | tr -d ' ' || true)"
    [ -n "$pv_list" ] || continue
    if echo "$pv_list" | grep -qv '^/dev/\(mapper/\)\?loop'; then
        continue
    fi
    run_best_effort vgchange -an "$vg"
    run_best_effort vgremove -f "$vg"
    for pv in $pv_list; do
        run_best_effort pvremove -ff -y "$pv"
        pv_name="${pv##*/}"
        pv_name="${pv_name%%p[0-9]*}"
        lvm_loop_devices="$lvm_loop_devices /dev/$pv_name"
    done
done

loop_devices="$(losetup -l --noheadings -O NAME,BACK-FILE 2>/dev/null | while read -r dev back; do
    back="${back% (deleted)}"
    case "$back" in
        "$build_dir"/*|"$dib_tmp"*) echo "$dev" ;;
        *) case " $lvm_loop_devices " in *" $dev "*) echo "$dev" ;; esac ;;
    esac
done || true)"

while IFS= read -r loop_dev; do
    [ -z "$loop_dev" ] && continue
    loop_name="${loop_dev##*/}"
    for dm_name in $(dmsetup ls 2>/dev/null | awk -v prefix="${loop_name}p" '$1 ~ "^" prefix "[0-9]+$" { print $1 }' || true); do
        run_best_effort dmsetup remove "$dm_name"
    done
done <<< "$loop_devices"

while IFS= read -r loop_dev; do
    [ -z "$loop_dev" ] || run_best_effort losetup -d "$loop_dev"
done <<< "$loop_devices"
