# group_vars/&lt;distro&gt;/main.yml

Each Ansible inventory group has a distro-specific variable file that overrides
defaults from `group_vars/all/main.yml`. The following groups are defined:

- `group_vars/ubuntu/main.yml`
- `group_vars/fedora/main.yml`
- `group_vars/centos10stream/main.yml`

All three files share the same variable structure. See the
[Per-Distro Differences](#per-distro-differences) section for values that vary.

---

## Build Environment

<!-- markdownlint-disable MD013 -->
| Variable | Value | Description |
| --- | --- | --- |
| `venv_bin` | path to venv `bin/` dir | Directory containing `disk-image-create` and related tools from the Python virtual environment. |
| `path` | `{{ venv_bin }}:{{ ansible_env.PATH }}` | Prepends the venv bin dir to `PATH` so venv binaries are found first. |
| `build_dir` | `/work/dib-builds` | Staging directory for all image files. Used by every playbook in the pipeline. |
<!-- markdownlint-enable MD013 -->

---

## Disk Image Builder (DIB) Settings

These variables are exported as environment variables when `disk-image-create`
is invoked in `playbooks/build-qcow2.yml`.

<!-- markdownlint-disable MD013 -->
| Variable | Value | Description |
| --- | --- | --- |
| `dib_block_device` | `gpt` | Partition table type. Exported as `DIB_BLOCK_DEVICE`. |
| `dib_block_device_config` | path to `block-device-efi-config.yml` | LVM/EFI block device layout file. Exported as `DIB_BLOCK_DEVICE_CONFIG`. |
| `dib_openssh_server_hardening` | `0` | Disables the DIB SSH hardening element. Exported as `DIB_OPENSSH_SERVER_HARDENING`. |
| `dib_cloud_init_datasources` | `None` | Disables cloud-init datasource detection. Exported as `DIB_CLOUD_INIT_DATASOURCES`. |
| `dib_bootloader_default_cmdline` | kernel parameters | Default kernel command line. Exported as `DIB_BOOTLOADER_DEFAULT_CMDLINE`. |
<!-- markdownlint-enable MD013 -->

The default kernel command line applied to all distros:

```text
biosdevname=0 iommu=on ipv6.disable=1 net.ifnames=0 dm_mod.use_blk_mq=Y scsi_mod.use_blk_mq=Y
```

---

## DIB Elements

DIB elements are the modular build components assembled by `disk-image-create`.

<!-- markdownlint-disable MD013 -->
| Variable | Value | Description |
| --- | --- | --- |
| `elements_base` | space-separated element names | Core elements passed as positional arguments to `disk-image-create`. Differs per distro. |
| `elements_path` | `../elements` | Path to the custom elements directory. Exported as `ELEMENTS_PATH`. |
| `elements_custom` | `custom-{{ target_group }}` | Distro-specific custom element appended after `elements_base`. |
<!-- markdownlint-enable MD013 -->

The `elements_base` for each group:

<!-- markdownlint-disable MD013 -->
| Group | `elements_base` |
| --- | --- |
| `ubuntu` | `bootloader block-device-efi-lvm ubuntu-minimal` |
| `fedora` | `bootloader block-device-efi-lvm fedora dracut-regenerate` |
| `centos10stream` | `bootloader block-device-efi-lvm centos dracut-regenerate` |
<!-- markdownlint-enable MD013 -->

---

## Virtual Machine Specifications

Used in `templates/ovf-file.j2` to generate the OVF descriptor for VMware.

<!-- markdownlint-disable MD013 -->
| Variable | Value | Description |
| --- | --- | --- |
| `vm_memory_mb` | `4096` | VM memory allocation in MB. |
| `vm_cpus` | `4` | Number of virtual CPUs. |
| `vm_os_type` | e.g. `ubuntu64Guest` | VMware guest OS identifier used in the OVF `OperatingSystemSection`. |
<!-- markdownlint-enable MD013 -->

---

## Swap Configuration

Controls whether a swap logical volume is created inside the built image.
The swap setup runs via `guestfish` in `playbooks/build-qcow2.yml` after the
image is built, conditionally on `add_swap`.

<!-- markdownlint-disable MD013 -->
| Variable | Value | Description |
| --- | --- | --- |
| `add_swap` | `true` | When `true`, enables the swap configuration task after image build. |
| `swap_device` | `/dev/mapper/vg1-lv_swap` | Block device path for the swap LV, added to `/etc/fstab` inside the image. |
| `swap_size` | `4096` | Swap LV size in MB, passed to `lvcreate`. |
<!-- markdownlint-enable MD013 -->

---

## VMware / vSphere

<!-- markdownlint-disable MD013 -->
| Variable | Value | Description |
| --- | --- | --- |
| `vm_network` | `VM Network` | Network name written into the OVF `NetworkSection`. |
| `vm_os_description` | e.g. `Ubuntu Linux (64-bit)` | Human-readable OS description written into the OVF `OperatingSystemSection`. |
| `vsphere_content_library` | `Content_Library` | Target vSphere content library for OVA import in `playbooks/import-ova-vsphere.yml`. |
<!-- markdownlint-enable MD013 -->

---

## GCP

<!-- markdownlint-disable MD013 -->
| Variable | Value | Description |
| --- | --- | --- |
| `gcp_import_image` | e.g. `ubuntu-2204` | Base image name used when importing to GCP in `playbooks/import-qcow2-gcp.yml`. |
<!-- markdownlint-enable MD013 -->

---

## Per-Distro Differences

Variables that differ across the three groups. All other variables are identical.

<!-- markdownlint-disable MD013 -->
| Variable | `ubuntu` | `fedora` | `centos10stream` |
| --- | --- | --- | --- |
| `venv_bin` | `~/venvs/diskimage-builder/venv/bin` | `~/.fedora/bin` | `~/venvs/diskimage-builder/venv/bin` |
| `elements_base` | `bootloader block-device-efi-lvm ubuntu-minimal` | `bootloader block-device-efi-lvm fedora dracut-regenerate` | `bootloader block-device-efi-lvm centos dracut-regenerate` |
| `vm_os_type` | `ubuntu64Guest` | `centos9_64Guest` | `centos9_64Guest` |
| `vm_os_description` | `Ubuntu Linux (64-bit)` | `Red Hat Fedora (64-bit)` | `CentOS 10 (64-bit)` |
| `gcp_import_image` | `ubuntu-2204` | `centos-stream-9` | `centos-stream-9` |
<!-- markdownlint-enable MD013 -->
