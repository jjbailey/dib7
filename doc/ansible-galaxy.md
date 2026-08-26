# Ansible Galaxy Collection List

The authoritative versions live in `requirements.yml`, pinned against
ansible-core 2.18.18. To install the pinned set in one step:

```bash
~/.dib7/bin/ansible-galaxy collection install -r requirements.yml
```

The per-collection commands below install the latest available version
instead, which may not match the pins. Use them for ad hoc checks.

Each collection declares a floor in its `meta/runtime.yml`. Against
ansible-core 2.18.18 the pinned set stands at:

| Collection        | Pinned | `requires_ansible` | Status |
| ----------------- | ------ | ------------------ | ------ |
| `amazon.aws`      | 11.4.0 | `>=2.17.0`         | OK     |
| `google.cloud`    | 1.13.0 | `>=2.16.0`         | OK     |
| `openstack.cloud` | 2.6.0  | `>=2.8`            | OK     |

To re-check after any upgrade:

```bash
grep -m1 requires_ansible \
  ~/.ansible/collections/ansible_collections/*/*/meta/runtime.yml
```

## Unpinned collections present on the build host

`community.general` (12.6.4) and `community.vmware` (5.10.0) are installed but
are not listed in `requirements.yml` and are not referenced by any playbook —
the vSphere workflows shell out to PowerShell helpers instead. Both declare
`requires_ansible: >=2.17.0`, so both are satisfiable on ansible-core 2.18.18
if a playbook ever starts using them.

---

## AWS

### 1. Verify AWS Collections

```bash
~/.dib7/bin/ansible-galaxy collection list | grep aws
```

### 2. Install AWS Collections

```bash
~/.dib7/bin/ansible-galaxy collection install amazon.aws [--force]
```

---

## GCP

### 1. Verify GCP Collections

```bash
~/.dib7/bin/ansible-galaxy collection list | grep google
```

### 2. Install GCP Collections

```bash
~/.dib7/bin/ansible-galaxy collection install google.cloud [--force]
```

---

## OpenStack

### 1. Verify OpenStack Collections

```bash
~/.dib7/bin/ansible-galaxy collection list | grep openstack
```

### 2. Install OpenStack Collections

```bash
~/.dib7/bin/ansible-galaxy collection install openstack.cloud [--force]
```

---

## VMware

The current vSphere playbooks shell out to local PowerShell helper scripts and
do not use Ansible VMware collections, so no additional Galaxy collections are
required for those workflows.
