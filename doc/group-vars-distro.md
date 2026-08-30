# group_vars/&lt;distro&gt;/main.yml

Each Ansible inventory group has a distro-specific variable file that overrides
defaults from `group_vars/all/main.yml`. The following groups are defined:

- `group_vars/centos/main.yml`
- `group_vars/debian/main.yml`
- `group_vars/fedora/main.yml`
- `group_vars/rocky/main.yml`
- `group_vars/ubuntu/main.yml`

All five files share the same variable structure. See the
[Per-Distro Differences](#per-distro-differences) section for values that vary.

---

## Build Environment

`venv_bin`, `path`, and `build_dir` are no longer per-distro. Every group
builds from the single `~/.dib7` virtualenv, so all three now live in
`group_vars/all/main.yml` — see [group-vars-all.md](group-vars-all.md) and
[python3-virtualenv.md](python3-virtualenv.md).

---

## Disk Image Builder (DIB) Settings

These variables are exported as environment variables when `disk-image-create`
is invoked in `playbooks/build-qcow2.yml`.

<!-- markdownlint-disable MD013 MD060 -->

| Variable                         | Value                                 | Description                                                                         |
| -------------------------------- | ------------------------------------- | ----------------------------------------------------------------------------------- |
| `dib_block_device`               | `gpt`                                 | Partition table type. Exported as `DIB_BLOCK_DEVICE`.                               |
| `dib_block_device_config`        | path to `block-device-efi-config.yml` | LVM/EFI block device layout file. Exported as `DIB_BLOCK_DEVICE_CONFIG`.            |
| `dib_openssh_server_hardening`   | `0`                                   | Disables the DIB SSH hardening element. Exported as `DIB_OPENSSH_SERVER_HARDENING`. |
| `dib_cloud_init_datasources`     | `None`                                | Disables cloud-init datasource detection. Exported as `DIB_CLOUD_INIT_DATASOURCES`. |
| `dib_bootloader_default_cmdline` | kernel parameters                     | Default kernel command line. Exported as `DIB_BOOTLOADER_DEFAULT_CMDLINE`.          |

<!-- markdownlint-enable MD013 MD060 -->

The default kernel command line applied to all distros:

```text
biosdevname=0 iommu=on ipv6.disable=1 net.ifnames=0 dm_mod.use_blk_mq=Y scsi_mod.use_blk_mq=Y
```

---

## DIB Elements

DIB elements are the modular build components assembled by `disk-image-create`.

<!-- markdownlint-disable MD013 MD060 -->

| Variable          | Value                         | Description                                                                              |
| ----------------- | ----------------------------- | ---------------------------------------------------------------------------------------- |
| `elements_base`   | space-separated element names | Core elements passed as positional arguments to `disk-image-create`. Differs per distro. |
| `elements_path`   | `../elements`                 | Path to the custom elements directory. Exported as `ELEMENTS_PATH`.                      |
| `elements_custom` | `custom-{{ target_group }}`   | Distro-specific custom element appended after `elements_base`.                           |

<!-- markdownlint-enable MD013 MD060 -->

The `elements_base` for each group:

<!-- markdownlint-disable MD013 -->

| Group    | `elements_base`                                                       |
| -------- | --------------------------------------------------------------------- |
| `centos` | `bootloader block-device-efi-lvm centos dracut-regenerate`            |
| `debian` | `bootloader block-device-efi-lvm debian-minimal`                      |
| `fedora` | `bootloader block-device-efi-lvm fedora dracut-regenerate`            |
| `rocky`  | `bootloader block-device-efi-lvm rocky-cloud-image dracut-regenerate` |
| `ubuntu` | `bootloader block-device-efi-lvm ubuntu-minimal`                      |

<!-- markdownlint-enable MD013 -->

---

## Virtual Machine Specifications

Used in `templates/ovf-file.j2` to generate the OVF descriptor for VMware.

<!-- markdownlint-disable MD013 -->

| Variable       | Value                | Description                                                                                                                                                                                 |
| -------------- | -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `vm_memory_mb` | `4096`               | VM memory allocation in MB.                                                                                                                                                                 |
| `vm_cpus`      | `4`                  | Number of virtual CPUs.                                                                                                                                                                     |
| `vm_os_type`   | e.g. `ubuntu64Guest` | VMware guest OS identifier used in the OVF `OperatingSystemSection`. Debian Trixie intentionally uses the Debian 12 guest ID because VMware does not yet expose a native Trixie identifier. |

<!-- markdownlint-enable MD013 -->

---

## Swap Configuration

Controls whether a swap logical volume is created inside the built image.
The swap setup runs via `guestfish` in `playbooks/build-qcow2.yml` after the
image is built, conditionally on `add_swap`.

<!-- markdownlint-disable MD013 -->

| Variable      | Value                     | Description                                                                |
| ------------- | ------------------------- | -------------------------------------------------------------------------- |
| `add_swap`    | `true`                    | When `true`, enables the swap configuration task after image build.        |
| `swap_device` | `/dev/mapper/vg1-lv_swap` | Block device path for the swap LV, added to `/etc/fstab` inside the image. |
| `swap_size`   | `4096`                    | Swap LV size in MB, passed to `lvcreate`.                                  |

<!-- markdownlint-enable MD013 -->

---

## VMware / vSphere

<!-- markdownlint-disable MD013 -->

| Variable                  | Value                          | Description                                                                                                                    |
| ------------------------- | ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------ |
| `vm_network`              | `VM Network`                   | Network name written into the OVF `NetworkSection`.                                                                            |
| `vm_os_description`       | e.g. `Ubuntu Linux (64-bit)`   | Human-readable OS description written into the OVF `OperatingSystemSection`.                                                   |
| `vsphere_content_library` | `Content_Library`              | Target vSphere content library for `import-ova-vsphere.yml` when creating the `vSphere OVA`.                                   |
| `vsphere_template_name`   | `inventory_hostname-base.tmpl` | Final vSphere template name used by `playbooks/import-ova-vsphere-template.yml` and `playbooks/recreate-vsphere-template.yml`. |

<!-- markdownlint-enable MD013 -->

---

## Per-Distro Differences

Variables that differ across the five groups. All other variables are identical.

<!-- markdownlint-disable MD013 MD060 -->

| Group    | `elements_base`                                                       | `vm_os_type`       | `vm_os_description`            |
| -------- | --------------------------------------------------------------------- | ------------------ | ------------------------------ |
| `centos` | `bootloader block-device-efi-lvm centos dracut-regenerate`            | `centos9_64Guest`  | `CentOS 10 (64-bit)`           |
| `debian` | `bootloader block-device-efi-lvm debian-minimal`                      | `debian12_64Guest` | `Debian GNU/Linux 12 (64-bit)` |
| `fedora` | `bootloader block-device-efi-lvm fedora dracut-regenerate`            | `centos9_64Guest`  | `Red Hat Fedora (64-bit)`      |
| `rocky`  | `bootloader block-device-efi-lvm rocky-cloud-image dracut-regenerate` | `centos9_64Guest`  | `Rocky Linux 10 (64-bit)`      |
| `ubuntu` | `bootloader block-device-efi-lvm ubuntu-minimal`                      | `ubuntu64Guest`    | `Ubuntu Linux (64-bit)`        |

<!-- markdownlint-enable MD013 MD060 -->

All five groups build from the same `~/.dib7` virtualenv. The Fedora patch it
carries touches only the `fedora` element, so it has no effect on the other
builds; see [fedora.md](fedora.md).
