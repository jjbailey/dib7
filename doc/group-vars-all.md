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

| Variable      | Default                                 | Description                                                                                    |
| ------------- | --------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `venv_bin`    | `{{ ansible_env.HOME }}/.dib7/bin`      | Directory holding `disk-image-create` and the other virtualenv tools.                          |
| `path`        | `{{ venv_bin }}:{{ ansible_env.PATH }}` | Prepends the virtualenv bin dir to `PATH` so its binaries are found first.                     |
| `build_dir`   | `/work/dib-builds`                      | Staging directory for all image files. Used by every playbook in the pipeline.                 |
| `dib_vg_name` | `vg1`                                   | LVM volume group name used by the block device config; also what the build cleanup tears down. |

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

## Output File Names

Derived from `image_name`. All output artifacts share the same base name with
different extensions.

<!-- markdownlint-disable MD013 -->

| Variable     | Value                    | Description                                        |
| ------------ | ------------------------ | -------------------------------------------------- |
| `mf_file`    | `{{ image_name }}.mf`    | OVA manifest file (SHA checksums).                 |
| `ova_file`   | `{{ image_name }}.ova`   | Final OVA archive.                                 |
| `ovf_file`   | `{{ image_name }}.ovf`   | OVF descriptor XML.                                |
| `qcow2_file` | `{{ image_name }}.qcow2` | QCOW2 disk image (primary build output).           |
| `vmdk_file`  | `{{ image_name }}.vmdk`  | VMDK disk image (converted from QCOW2 for VMware). |

<!-- markdownlint-enable MD013 -->

---

## Pipeline Stamps

Each stage writes a stamp holding the `run_id` that produced the artifact next
to it, and the following stage refuses to consume an artifact whose stamp is
missing or from an older run. See `local/pipeline-stamps.md` (internal-only,
not part of the public dib7 mirror).

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

| Variable                        | Default                              | Description                                                                                   |
| ------------------------------- | ------------------------------------ | --------------------------------------------------------------------------------------------- |
| `aws_import_boot_mode`          | `{{ image_boot_mode }}`              | Boot mode handed to AWS `ImportImage`. Separate only because the API takes it as a parameter. |
| `gcp_replace_existing_image`    | `true`                               | Delete and recreate a GCP image of the same name rather than failing.                         |
| `gcp_delete_qcow2_after_import` | `false`                              | Whether to remove the staged QCOW2 from GCS after a successful import.                        |
| `vsphere_template_name`         | `{{ inventory_hostname }}-base.tmpl` | Name of the template created in the `Templates` folder.                                       |

<!-- markdownlint-enable MD013 -->

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

Group files add distro-specific variables (DIB elements, venv paths, VMware
guest type, GCP base image, swap config, etc.) and may shadow any variable
defined here.
