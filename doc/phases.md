# Phase Subdirectories

<https://docs.openstack.org/diskimage-builder/latest/developer/developing_elements.html>

Make as many of the following subdirectories as you need, depending on what
part of the process you need to customise. The subdirectories are executed
in the order given here. Scripts within the subdirectories should be named
with a two-digit numeric prefix, and are executed in numeric order.

Only files which are marked executable (+x) will be run, so other files can be
stored in these directories if needed. As a convention, we try to only store
executable scripts in the phase subdirectories and store data files elsewhere
in the element.

Depending on which directory is in play, the scripts either in or out of chroot.
Refer to the link above for details.

## The phases are

| # | Phase | Chroot |
| --- | ------- | -------- |
| 1 | root.d | outside |
| 2 | extra-data.d | outside |
| 3 | pre-install.d | inside |
| 4 | install.d | inside |
| 5 | post-install.d | inside |
| 6 | post-root.d | outside |
| 7 | block-device.d | outside |
| 8 | pre-finalise.d | outside |
| 9 | finalise.d | inside |
| 10 | cleanup.d | outside |
