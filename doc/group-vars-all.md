# group_vars/all/main.yml

Default variables applied to **all hosts**. These are the baseline values for
the dib7 disk image build pipeline. Group-specific files (e.g.
`group_vars/debian/main.yml` or `group_vars/ubuntu/main.yml`) can override any
of these.

---

## Build Environment

Every distro builds from the single `~/.dib7` virtualenv, so these are defined
once here rather than per group. See
[python3-virtualenv.md](python3-virtualenv.md).

<!-- markdownlint-disable MD013 -->

| Variable      | Default                                 | Description                                                                                                                                                                                                                                                                       |
| ------------- | --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `venv_bin`    | `{{ ansible_env.HOME }}/.dib7/bin`      | Directory holding `disk-image-create` and the other virtualenv tools.                                                                                                                                                                                                             |
| `path`        | `{{ venv_bin }}:{{ ansible_env.PATH }}` | Prepends the virtualenv bin dir to `PATH` so its binaries are found first.                                                                                                                                                                                                        |
| `build_dir`   | `/work/dib-builds`                      | Staging directory for all image files. Used by every playbook in the pipeline.                                                                                                                                                                                                    |
| `dib_vg_name` | `vg1`                                   | Name of the LVM volume group the build creates. Used by `bin/cleanup-dib-build.sh` and to build `swap_device`. It must stay `vg1`: `block-device-config/block-device-efi-config.yml` hard-codes that name and is not templated, so changing this variable alone breaks the build. |

<!-- markdownlint-enable MD013 -->

---

## Image Identity

<!-- markdownlint-disable MD013 -->

| Variable     | Default                         | Description                                                          |
| ------------ | ------------------------------- | -------------------------------------------------------------------- |
| `image_arch` | `amd64`                         | Target CPU architecture for the image build.                         |
| `image_name` | `{{ inventory_hostname }}-base` | Base name for all output files, derived from the inventory hostname. |
| `image_size` | `35`                            | Disk image size in GB.                                               |
| `image_type` | `qcow2`                         | Primary output format (passed to `disk-image-create`).               |

<!-- markdownlint-enable MD013 -->

---

## Distro-Independent Build Settings

Every group builds with the same block device layout, kernel command line,
element path, VM sizing, swap and network, so these are defined here rather
than repeated in each `group_vars/<group>/main.yml`. Only `elements_base`,
`image_ssh_username`, `vm_os_type` and `vm_os_description` differ per distro - see
[group-vars-distro.md](group-vars-distro.md).

<!-- markdownlint-disable MD013 -->

| Variable                         | Default                                                                          | Description                                                                                                                       |
| -------------------------------- | -------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `dib_block_device`               | `gpt`                                                                            | Partition table type, exported as `DIB_BLOCK_DEVICE`.                                                                             |
| `dib_block_device_config`        | `block-device-efi-config.yml`                                                    | LVM/EFI block device layout, looked up from the example files in `block-device-config/`; copy or replace one for your deployment. |
| `dib_openssh_server_hardening`   | `0`                                                                              | Disables the DIB SSH hardening element.                                                                                           |
| `dib_cloud_init_datasources`     | `None`                                                                           | Disables cloud-init datasource detection.                                                                                         |
| `dib_bootloader_default_cmdline` | `biosdevname=0 iommu=on net.ifnames=0 dm_mod.use_blk_mq=Y scsi_mod.use_blk_mq=Y` | Default kernel command line.                                                                                                      |
| `elements_path`                  | `../elements`                                                                    | Exported as `ELEMENTS_PATH` for the in-tree elements.                                                                             |
| `elements_custom`                | `custom-{{ target_group }}`                                                      | The distro's own element, appended after `elements_base`.                                                                         |
| `vm_memory_mb`                   | `4096`                                                                           | VM memory in MB, written into the OVF descriptor.                                                                                 |
| `vm_cpus`                        | `4`                                                                              | Virtual CPUs, written into the OVF descriptor.                                                                                    |
| `add_swap`                       | `true`                                                                           | Create a swap LV inside the image (via `guestfish`) after the build.                                                              |
| `swap_device`                    | `/dev/mapper/{{ dib_vg_name }}-lv_swap`                                          | Swap LV path added to `/etc/fstab` inside the image.                                                                              |
| `swap_size`                      | `4096`                                                                           | Swap LV size in MB.                                                                                                               |
| `vm_network`                     | `VM Network`                                                                     | Network name written into the OVF `NetworkSection`.                                                                               |

<!-- markdownlint-enable MD013 -->

`dib_block_device_config` is read with the `file` lookup, whose relative paths
resolve against the playbook directory (`playbooks/`) - which is why the value
starts with `../`. The files in `../block-device-config/` are examples and
starting points; copy or replace one to make the end-user choice.

---

## Output File Names

Derived from `image_name`. All output artifacts share the same base name with
different extensions.

<!-- markdownlint-disable MD013 -->

| Variable     | Value                    | Description                                        |
| ------------ | ------------------------ | -------------------------------------------------- |
| `ova_file`   | `{{ image_name }}.ova`   | Final OVA archive.                                 |
| `ovf_file`   | `{{ image_name }}.ovf`   | OVF descriptor XML.                                |
| `qcow2_file` | `{{ image_name }}.qcow2` | QCOW2 disk image (primary build output).           |
| `vmdk_file`  | `{{ image_name }}.vmdk`  | VMDK disk image (converted from QCOW2 for VMware). |

<!-- markdownlint-enable MD013 -->

---

## Pipeline Stamps

Each stage writes a stamp holding the `run_id` that produced the artifact next
to it, and the following stage refuses to consume an artifact whose stamp is
missing or from an older run.

<!-- markdownlint-disable MD013 -->

| Variable             | Value                        | Description                                                           |
| -------------------- | ---------------------------- | --------------------------------------------------------------------- |
| `build_stamp_file`   | `{{ image_name }}.built`     | Written by `build-qcow2.yml`; verified by the QCOW2 consumers.        |
| `convert_stamp_file` | `{{ image_name }}.converted` | Written by `convert-qcow2-to-ova.yml`; verified by the OVA consumers. |

<!-- markdownlint-enable MD013 -->

---

## Image Catalog

The Terraform integration contract. See [image-catalog.md](image-catalog.md).

<!-- markdownlint-disable MD013 -->

| Variable             | Default                                           | Description                                                                                                     |
| -------------------- | ------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `image_catalog_path` | `{{ inventory_dir }}/catalogs/image-catalog.json` | Where the catalog is written - `catalogs/` in the repo. Override when the catalog is copied to release storage. |
| `catalog_version`    | `run_id`, else the verified stamp                 | Version recorded on each entry. Falls back to the run recorded in the stage stamp when no `run_id` was passed.  |
| `image_boot_mode`    | `uefi`                                            | Boot mode recorded on every catalog entry. A property of the image, not of a provider.                          |

<!-- markdownlint-enable MD013 -->

---

## Cloud Import Behaviour

<!-- markdownlint-disable MD013 -->

| Variable                        | Default                 | Description                                                                                       |
| ------------------------------- | ----------------------- | ------------------------------------------------------------------------------------------------- |
| `aws_import_boot_mode`          | `{{ image_boot_mode }}` | Boot mode handed to AWS `ImportImage`. Separate only because the API takes it as a parameter.     |
| `gcp_import_location`           | `us-central1`           | Region where the GCP import job runs. A `gcp_projects` entry in `vaults/gcp.yml` can override it. |
| `gcp_replace_existing_image`    | `true`                  | Delete and recreate a GCP image of the same name rather than failing.                             |
| `gcp_delete_qcow2_after_import` | `false`                 | Whether to remove the staged QCOW2 from GCS after a successful import.                            |

<!-- markdownlint-enable MD013 -->

---

## OVF Metadata

These shared defaults populate the OVF descriptor. A distro can override them
when VMware requires a different numeric guest identifier.

| Variable         | Default | Description                                     |
| ---------------- | ------- | ----------------------------------------------- |
| `ovf_os_id`      | `107`   | Numeric operating-system identifier in the OVF. |
| `ovf_os_version` | `7`     | Version value written into the OVF metadata.    |

---

## vSphere Defaults

The content library and template placement defaults can be overridden by
`vaults/vsphere.yml`.

| Variable                  | Default                              | Description                                 |
| ------------------------- | ------------------------------------ | ------------------------------------------- |
| `vsphere_content_library` | `Content_Library`                    | Content library used by vSphere imports.    |
| `vsphere_template_name`   | `{{ inventory_hostname }}-base.tmpl` | Template name created from the OVA.         |
| `vsphere_template_folder` | `Templates`                          | Inventory folder receiving the template.    |
| `vsphere_template_host`   | empty                                | Optional ESXi host for template deployment. |

---

## Package Manager / APT Behaviour

These suppress interactive prompts during Debian/Ubuntu package operations.
They are harmless on RPM-based systems where `apt`/`dpkg` are not used.

<!-- markdownlint-disable MD013 -->

| Variable           | Value                                                                   | Description                                                                                    |
| ------------------ | ----------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `dpkg_opts`        | `-o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold` | Keeps existing config files without prompting when a package upgrade ships a new default.      |
| `debian_frontend`  | `noninteractive`                                                        | Prevents `apt`/`dpkg` from opening interactive dialogs (e.g. `debconf`).                       |
| `needrestart_mode` | `a`                                                                     | Sets `needrestart` to automatic mode so it restarts services without prompting after upgrades. |

<!-- markdownlint-enable MD013 -->

---

## Override Hierarchy

```text
group_vars/all/main.yml          ← these defaults
group_vars/<group>/main.yml      ← per-distro overrides (see note below)
host_vars/<host>/...             ← per-host overrides (if any)
```

The per-distro directories are `group_vars/debian/`, `group_vars/ubuntu/`,
`group_vars/fedora/`, `group_vars/rocky/`, and `group_vars/centos/`. Each one
is named for the inventory group in `hosts.yml` that it serves, which is what
lets Ansible load it automatically — keep those names in step when adding a
distro. See
[adding-distros-and-releases.md](adding-distros-and-releases.md).

Group files define only what differs per distro - `elements_base`,
`image_ssh_username`, `vm_os_type` and `vm_os_description` - and may shadow any variable defined
here. See [group-vars-distro.md](group-vars-distro.md).
