# GCP Supported Linux Distributions

Mirrors the "Supported operating systems" table for Migrate to Virtual Machines.
Last checked against upstream on 2026-07-28.

<https://cloud.google.com/migrate/virtual-machines/docs/5.0/discover/supported-os-versions>

`playbooks/import-qcow2-gcp.yml` imports through `gcloud migration vms
image-imports create`, which is Migrate to Virtual Machines (M2VM), so this is
the table that applies. The older `gcloud compute images import` path has a
different support matrix and is not what this repo uses.

## Import behavior

- M2VM performs "OS adaptation" on import: it modifies the guest so it boots and
  runs on Compute Engine. There is a skip toggle, but it is not recommended.
- Accepted formats include QCOW2, which is why this playbook uploads the qcow2
  directly rather than converting to VMDK the way the vSphere and AWS paths do.
  VMDK is documented as faster, if import time ever becomes a concern.
- 64-bit x86 only.
- The upstream tables carry a "BIOS to UEFI conversion supported" column. That
  is an opt-in security upgrade for BIOS-booting source VMs, not a constraint on
  images that are already UEFI. Every image in this repo is built UEFI-native
  from `block-device-efi-config.yml`, so that column does not apply.
- Distributions absent from the table are not declared unsupported. Google takes
  requests at <m2vm-os-support-request@google.com>.

## AlmaLinux

- 8.3–8.10
- 9.0–9.8
- 10.0–10.2

## CentOS Stream

- CentOS Stream 9
- CentOS Stream 10

CentOS Stream 8 has been dropped from the table since this doc was last written.

## Debian

- Debian 11.0–11.7
- Debian 12.0–12.10
- Debian 13.0–13.2

## Red Hat Enterprise Linux (RHEL)

- RHEL 7.9
- RHEL 8.0–8.10
- RHEL 9.0–9.7
- RHEL 10.0–10.2

Standard and SAP variants are both listed.

## Rocky Linux

- Rocky Linux 8.4–8.10
- Rocky Linux 9.0–9.7
- Rocky Linux 10.0–10.1

## Ubuntu

- Ubuntu 22.04
- Ubuntu 24.04
- Ubuntu 26.04

Ubuntu 18.04 and 20.04 have been dropped from the table since this doc was last
written.

## Supported by partners

Listed separately under "Operating systems supported by partners":

- Oracle Linux 6.0–10.1
- Amazon Linux

## Coverage of the images built here

| Build         | GCP            | Notes                                            |
| ------------- | -------------- | ------------------------------------------------ |
| `centos10s`   | Yes            | CentOS Stream 10                                 |
| `debian1215`  | Yes            | Debian 12.x                                      |
| `debian1306`  | Yes            | Debian 13.x, in range through 13.2               |
| `fedora44`    | **Not listed** | Fedora does not appear in the table at all       |
| `rocky102`    | Yes            | Confirm the point release lands at or below 10.1 |
| `ubuntu24044` | Yes            | Known good, imports successfully                 |
| `ubuntu26041` | Yes            | Supported here, unlike AWS — see below           |

Fedora is absent from the M2VM table entirely, in contrast to AWS, which lists
Fedora 41–43. `fedora44` is therefore off-matrix on both clouds.

## Ubuntu 26.04 imports to GCP but not to AWS

GCP lists Ubuntu 26.04 as supported. AWS also lists it, but its import fails
during the injection stage with a `SERVER_ERROR` — see
[aws-supported-images.md](aws-supported-images.md). If a 26.04 image is needed in
a cloud before that is resolved, GCP is the path that works today.

The reverse holds for Debian 13: supported here, but AWS stops at 12.7.
