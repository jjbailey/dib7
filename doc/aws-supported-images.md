# AWS Supported Linux Distributions

Mirrors the "Operating systems supported by VM Import/Export" table in the AWS
docs. Last checked against upstream on 2026-07-28.

<https://docs.aws.amazon.com/vm-import/latest/userguide/prerequisites.html>

AWS matches on the _kernel_ version, not just the release, so the kernel column
matters. An import whose kernel is off the matrix comes back as
`ClientError: Unsupported kernel version`.

## General constraints

- ARM64 VMs are not supported. Every build here is amd64, so this is moot today.
- i386 support ended 2026-04-01. Also moot here.
- Imported VMs should use distro default kernels; custom kernels may not convert.
- Predictable network interface names are not supported. Handled by the
  `net.ifnames=0 biosdevname=0` arguments in `dib_bootloader_default_cmdline`.
- UEFI Linux imports need a fallback `BOOTX64.EFI` on the ESP. Handled by the
  bootloader element's `grub-install --removable --target=x86_64-efi`.
- MBR and GPT volumes are both supported, formatted ext2/3/4, Btrfs, JFS or XFS.
  Btrfs subvolumes are not supported.

## Amazon Linux

- Amazon Linux 2023 — 6.1
- Amazon Linux 2 — 4.14, 4.19, 5.4, 5.10

## CentOS

- CentOS 9 (Stream) — 5.14.0
- CentOS 5.1–5.11, 6.1–6.8, 7.0–7.9, 8.0–8.2 are all EOL per AWS; listed, but
  not recommended for new imports

## Debian

- Debian 11 — 5.10.0
- Debian 12.2, 12.4, 12.7 — 6.1.0
- Debian 6.0.0–6.0.8, 7.0.0–7.8.0, 10 are EOL per AWS

Note that Debian 13 (trixie) is not yet listed, which `debian1306` builds.

## Fedora

- Fedora 41 — 6.11.4
- Fedora 42 — 6.14.0
- Fedora 43 — 6.17.1
- Fedora 18, 19, 20, 37–40 are EOL per AWS

Note that Fedora 44 is not yet listed, which `fedora44` builds.

## Oracle Linux

- Oracle Linux 7.0–7.6 — RHCK 3.10.0, UEK 3.8.13/4.1.12/4.14.35/5.4.17
- Oracle Linux 8.0–8.9 — RHCK 4.18.0, UEK 5.15.0 (el8uek)
- Oracle Linux 9.0–9.5 — RHCK 5.14.0/5.15.0, UEK 5.15.0 (el9uek)
- Oracle Linux 9.6–9.7 — RHCK 5.14.0, UEK 6.12.0 (el9uek)
- Oracle Linux 10.0–10.1 — RHCK 6.12.0, UEK 6.12.0 (el10uek)

## Red Hat Enterprise Linux (RHEL)

- RHEL 7 — 3.10.0
- RHEL 8.0–8.9 — 4.18.0
- RHEL 9.0–9.7 — 5.14.0
- RHEL 10.0–10.1 — 6.12.0

## Rocky Linux

- Rocky Linux 9.0–9.7 — 5.14.0
- Rocky Linux 10.0–10.1 — 6.12.0

## Ubuntu

- Ubuntu 18.04 — 4.15.0, 5.4.0
- Ubuntu 20.04 — 5.4.0
- Ubuntu 22.04 — 5.15.0
- Ubuntu 23.04 — 5.15.0
- Ubuntu 24.04 — 6.8.0, 6.11.0
- Ubuntu 25.10 — 6.17.0
- Ubuntu 26.04 — 7.0.0

## Known issues

### Ubuntu 26.04 fails during injection

As of 2026-07-28, importing `ubuntu26041-base.ova` fails even though 26.04 with
kernel 7.0.0 is on the matrix above and the build produces exactly
`linux-image-7.0.0-28-generic`:

```text
"status": "deleted",
"status_message": "SERVER_ERROR : injection : AWS initiated task cancellation"
```

Snapshot conversion completes first, so the disk and the streamOptimized VMDK
are fine. The failure is in the injection stage, where AWS activates the LVM
volume group, installs ENA/NVMe drivers and rewrites grub.

`SERVER_ERROR` is an AWS-side crash, not a rejection. Anything AWS detects as an
image problem comes back as a `ClientError` instead. Diffing the 26.04 and 24.04
build logs turns up no structural difference — same disk layout, same EFI
bootloader install, same initramfs-tools initrd, same kernel arguments. The only
deltas are the release itself and grub 2.14 vs 2.12, so the likely cause is that
the injection tooling does not yet handle 26.04 despite the docs table listing
it.

Options, in order:

1. Retry once, in case it is transient.
2. Bypass injection with `aws ec2 import-snapshot` plus `aws ec2 register-image
--boot-mode uefi --ena-support`. There is no `ec2_snapshot_import` module in
   amazon.aws 11.4.0, so this means shelling out. Confirm `ena` and `nvme` are
   in the initramfs first.
3. Open an AWS support case with the import task ID. A `SERVER_ERROR` is their
   bug to fix.

GCP lists and imports Ubuntu 26.04 without trouble, so if the image is needed in
a cloud before AWS is fixed, that is the path that works today. See
[gcp-supported-images.md](gcp-supported-images.md).
