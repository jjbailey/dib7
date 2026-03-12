# group_vars/all/main.yml

Default variables applied to **all hosts**. These are the baseline values for
the dib7 disk image build pipeline. Group-specific files (e.g.
`group_vars/ubuntu/main.yml`) can override any of these.

---

## Image Identity

<!-- markdownlint-disable MD013 -->
| Variable | Default | Description |
| --- | --- | --- |
| `image_arch` | `amd64` | Target CPU architecture for the image build. |
| `image_name` | `{{ inventory_hostname }}-base` | Base name for all output files, derived from the inventory hostname. |
| `image_size` | `35` | Disk image size in GB. |
| `image_type` | `qcow2` | Primary output format (passed to `disk-image-create`). |
<!-- markdownlint-enable MD013 -->

---

## Output File Names

Derived from `image_name`. All output artifacts share the same base name with
different extensions.

<!-- markdownlint-disable MD013 -->
| Variable | Value | Description |
| --- | --- | --- |
| `mf_file` | `{{ image_name }}.mf` | OVA manifest file (SHA checksums). |
| `ova_file` | `{{ image_name }}.ova` | Final OVA archive. |
| `ovf_file` | `{{ image_name }}.ovf` | OVF descriptor XML. |
| `qcow2_file` | `{{ image_name }}.qcow2` | QCOW2 disk image (primary build output). |
| `vmdk_file` | `{{ image_name }}.vmdk` | VMDK disk image (converted from QCOW2 for VMware). |
<!-- markdownlint-enable MD013 -->

---

## Package Manager / APT Behaviour

These suppress interactive prompts during Debian/Ubuntu package operations.
They are harmless on RPM-based systems where `apt`/`dpkg` are not used.

<!-- markdownlint-disable MD013 -->
| Variable | Value | Description |
| --- | --- | --- |
| `dpkg_opts` | `--force-confdef --force-confold` | Keeps existing config files without prompting when a package upgrade ships a new default. |
| `debian_frontend` | `noninteractive` | Prevents `apt`/`dpkg` from opening interactive dialogs (e.g. `debconf`). |
| `needrestart_mode` | `a` | Sets `needrestart` to automatic mode so it restarts services without prompting after upgrades. |
<!-- markdownlint-enable MD013 -->

---

## Override Hierarchy

```text
group_vars/all/main.yml          ← these defaults
group_vars/<group>/main.yml      ← per-distro overrides (ubuntu, fedora, centos10stream)
host_vars/<host>/...             ← per-host overrides (if any)
```

Group files add distro-specific variables (DIB elements, venv paths, VMware
guest type, GCP base image, swap config, etc.) and may shadow any variable
defined here.
