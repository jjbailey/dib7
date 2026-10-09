# AWS Supported Linux Distributions

Mirrors the "Operating systems supported by VM Import/Export" table in the AWS
docs. Last checked against upstream on 2026-10-04. Treat releases not listed
below as unsupported for this pipeline, even if a local import happens to work.

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

Note that Debian 13 (trixie) is not yet listed, which `debian1307` builds.

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

## Coverage of the images built here

<!-- markdownlint-disable MD013 -->

| Build         | AWS                     | Notes                                                                                  |
| ------------- | ----------------------- | -------------------------------------------------------------------------------------- |
| `centos10s`   | **Not listed**          | Upstream lists CentOS Stream 9 only                                                    |
| `debian1215`  | **Not listed**          | The rolling `bookworm` point release is not one of the listed 12.2 / 12.4 / 12.7       |
| `debian1307`  | **Not listed**          | Upstream stops at Debian 12.7                                                          |
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
