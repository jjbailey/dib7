# AWS Supported Linux Distributions

Mirrors the Linux/Unix rows in the "Operating systems supported by VM
Import/Export" table in the AWS docs. Last checked against upstream on
2026-10-17. The table also contains Windows rows, which this page omits. Treat
DIB7 target releases not listed in the coverage table below as off-matrix for
this pipeline, even if a local import happens to work.

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

- CentOS 5.1–5.11 — 2.6.18
- CentOS 6.1–6.8 — 2.6.32
- CentOS 7.0–7.9 — 3.10.0
- CentOS 8.0–8.2 — 4.18.0
- CentOS 9 — 5.14.0

CentOS 5–8 are EOL per AWS and are not recommended for new imports.

## Debian

- Debian 11 — 5.10.0
- Debian 12.2, 12.4, 12.7 — 6.1.0
- Debian 13.6 — 6.12.0

Debian 6, 7, and 10 are EOL per AWS.

AWS now lists Debian 13.6 with kernel 6.12.0. Check the built `debian1307`
image's point release and kernel against that row before importing.

## Fedora

- Fedora 41 — 6.11.4
- Fedora 42 — 6.14.0
- Fedora 43 — 6.17.1
- Fedora 18, 19, 20, 37–40 are EOL per AWS

Note that Fedora 44 is not yet listed, which `fedora44` builds.

## Oracle Linux

- Oracle Linux 5.10–5.11 — UEK el5uek kernel suffixes
- Oracle Linux 6.1–6.10 — RHCK 2.6.32/2.6.39; UEK 3.8.13/4.1.12
- Oracle Linux 7.0–7.6 — RHCK 3.10.0, UEK 3.8.13/4.1.12/4.14.35/5.4.17
- Oracle Linux 8.0–8.9 — RHCK 4.18.0, UEK 5.15.0 (el8uek)
- Oracle Linux 9.0–9.5 — RHCK 5.14.0/5.15.0, UEK 5.15.0 (el9uek)
- Oracle Linux 9.6–9.7 — RHCK 5.14.0, UEK 6.12.0 (el9uek)
- Oracle Linux 10.0–10.1 — RHCK 6.12.0, UEK 6.12.0 (el10uek)

Oracle Linux 5 and 6 are EOL per AWS.

## Red Hat Enterprise Linux (RHEL)

- RHEL 5 — 2.6.18
- RHEL 6 — 2.6.32 (except 2.6.32-71)
- RHEL 7 — 3.10.0
- RHEL 8.0–8.9 — 4.18.0
- RHEL 9.0–9.7 — 5.14.0
- RHEL 10.0–10.1 — 6.12.0

RHEL 5 and 6 are EOL per AWS.

## Rocky Linux

- Rocky Linux 9.0–9.7 — 5.14.0
- Rocky Linux 10.0–10.1 — 6.12.0

## Ubuntu

- Ubuntu 12.04 — 3.2.0
- Ubuntu 12.10 — 3.5.0
- Ubuntu 13.04 — 3.8.0
- Ubuntu 13.10 — 3.11
- Ubuntu 14.04 — 3.13.0, 3.16.0, 3.19.0
- Ubuntu 14.10 — 3.16
- Ubuntu 15.04 — 3.19.0
- Ubuntu 16.04 — 4.2.0, 4.4.0, 4.8.0, 4.10.0, 4.15.0
- Ubuntu 16.10 — 4.8.0
- Ubuntu 17.04 — 4.10.0
- Ubuntu 18.04 — 4.15.0, 5.4.0
- Ubuntu 20.04 — 5.4.0
- Ubuntu 22.04 — 5.15.0
- Ubuntu 23.04 — 5.15.0
- Ubuntu 24.04 — 6.8.0, 6.11.0
- Ubuntu 25.10 — 6.17.0
- Ubuntu 26.04 — 7.0.0

Ubuntu 12.04–17.04 are EOL per AWS. VM Import/Export stopped supporting i386
on 2026-04-01; the legacy entries are only relevant to supported 64-bit images.

## SUSE Linux Enterprise Server (SLES)

- SLES 11 — 2.6.32.12 (SP1), 3.0.13 (SP2), 3.0.76/3.0.101 (SP3), 3.0.101 (SP4)
- SLES 12 — 3.12.28 (no SP), 3.12.49 (SP1), 4.4 (SP2/SP3), 4.12 (SP4/SP5)
- SLES 15 — 4.12 (no SP/SP1), 5.3 (SP2/SP3), 5.14.21 (SP4/SP5), 6.4 (SP6)

SLES 11 and 12 are EOL per AWS.

## Coverage of the images built here

<!-- markdownlint-disable MD013 -->

| Build         | AWS                     | Notes                                                                                  |
| ------------- | ----------------------- | -------------------------------------------------------------------------------------- |
| `centos10s`   | **Not listed**          | Upstream lists CentOS Stream 9 only                                                    |
| `debian1215`  | **Not listed**          | The rolling `bookworm` point release is not one of the listed 12.2 / 12.4 / 12.7       |
| `debian1307`  | **Check point/kernel**  | AWS lists Debian 13.6 with kernel 6.12.0; verify the rolling `trixie` build matches    |
| `fedora44`    | **Not listed**          | Upstream lists Fedora 41–43                                                            |
| `rocky102`    | **Check point release** | AWS lists Rocky 10.0–10.1; this rolling target's exact point release must be confirmed |
| `ubuntu24045` | Yes                     | Upstream lists Ubuntu 24.04                                                            |
| `ubuntu26041` | Yes                     | Ubuntu 26.04 is listed with kernel 7.0.0; confirm the built kernel matches             |

<!-- markdownlint-enable MD013 -->

This mirrors the "Coverage of the images built here" table in
[gcp-supported-images.md](gcp-supported-images.md). The README links here rather
than repeating it.

## Known issues

Ubuntu 26.04 is listed by both AWS and GCP. AWS lists kernel 7.0.0, so verify
the kernel in the built image before importing. The `aws_import` inventory
group includes Ubuntu and Rocky; group membership alone does not establish
vendor support for the actual release and kernel produced by a rolling build.
