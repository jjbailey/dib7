# Adding Distros and Releases

This document covers the two common extension paths in `dib7`:

1. adding a new version of an existing distro family, such as Ubuntu `26.04`
2. adding a brand-new distro family, such as a new top-level inventory group

Use this together with:

- `hosts.yml`
- `group_vars/all/main.yml`
- `group_vars/<distro>/main.yml`
- `doc/group-vars-all.md`
- `doc/group-vars-distro.md`

## How Distro Selection Works

`dib7` separates distro-family settings from release-specific settings:

- `group_vars/all/main.yml` provides defaults shared by every build
- `group_vars/<distro>/main.yml` provides per-distro settings such as DIB
  elements and VMware metadata
- `hosts.yml` selects the concrete release with `dib_release`

During `playbooks/build-qcow2.yml`, Ansible exports `dib_release` as
`DIB_RELEASE` when calling `disk-image-create`.

That means:

- a new version of an existing distro usually only needs a new inventory
  host entry
- a new distro family usually needs inventory, `group_vars`, and a custom element

## Adding a New Version of an Existing Distro

Example: adding Ubuntu `26.04` with DIB release `resolute`.

1. Add a new host entry under the existing distro group in `hosts.yml`.

```yaml
ubuntu:
  hosts:
    ubuntu26040:
      ansible_connection: local
      dib_release: resolute
  vars:
    target_group: ubuntu
```

1. Reuse the existing distro-level variables in `group_vars/<distro>/main.yml`.

For Ubuntu, the common settings already live in `group_vars/ubuntu/main.yml`, so
you do not need a new `group_vars` file just to add another Ubuntu release.

1. Update any release-specific behavior in `elements/custom-<distro>/` if the
   new release changes package names, repo layout, boot behavior, or first-boot
   setup.

1. Refresh the docs that list supported releases.

Typical places:

- `README.md`
- `doc/aws-supported-images.md`
- `doc/gcp-supported-images.md`

1. Build just the new host to verify the release.

```bash
ansible-playbook playbooks/build-qcow2.yml -l ubuntu26040
```

## Adding a New Distro Family

Adding a new distro family is more than adding a host. The repo needs a new
inventory group, new per-distro variables, and usually a new custom element.

1. Add a new top-level inventory group in `hosts.yml`.

```yaml
newdistro:
  hosts:
    newdistro10:
      ansible_connection: local
      dib_release: "10"
  vars:
    target_group: newdistro
```

1. Create `group_vars/newdistro/main.yml`.

Start from the closest existing file in `group_vars/` and set at least:

- `venv_bin`
- `elements_base`
- `vm_os_type`
- `vm_os_description`

See `doc/group-vars-distro.md` for the shared structure and the variables that
can differ by distro.

1. Create `elements/custom-newdistro/`.

This is where distro-specific package configuration, cleanup, and image tuning
should live. Reuse the nearest existing custom element as a template.

1. Confirm the selected DIB elements support that distro family.

In particular, verify that `elements_base` references valid upstream DIB
elements for the target distro.

1. Check provider-specific constraints.

Examples:

- cloud import support may lag the distro's upstream release
- VMware may not have a native guest ID yet, in which case use the closest
  compatible value until support appears

1. Update documentation in `README.md` and any provider support docs under
   `doc/`.

1. Run a targeted build for the new host and inspect the output before adding it
   to broader automation.

## Checklist

Use this quick checklist before considering the work done:

- `hosts.yml` has the new host entry and correct `dib_release`
- `target_group` matches the intended distro family
- `group_vars/<distro>/main.yml` exists and has the right DIB/VMware settings
- `elements/custom-<distro>/` exists and still works for the new release
- supported-release docs are updated
- `ansible-playbook playbooks/build-qcow2.yml -l <host>` succeeds

## Rule of Thumb

If you are adding another release of a distro that already exists in `dib7`,
start with `hosts.yml`.

If you are adding a distro that does not yet exist in `dib7`, start with
`group_vars/` and `elements/`, then add the inventory group in `hosts.yml`.
