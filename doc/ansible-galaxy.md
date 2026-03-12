# Ansible Galaxy Collection List

---

## AWS

### 1. Verify AWS Collections

```bash
ansible-galaxy collection list | grep aws
```

### 2. Install AWS Collections

```bash
ansible-galaxy collection install amazon.aws [--force]
```

---

## GCP

### 1. Verify GCP Collections

```bash
ansible-galaxy collection list | grep google
```

### 2. Install GCP Collections

```bash
ansible-galaxy collection install google.cloud [--force]
```

---

## OpenStack

### 1. Verify OpenStack Collections

```bash
ansible-galaxy collection list | grep openstack
```

### 2. Install OpenStack Collections

```bash
ansible-galaxy collection install openstack.cloud [--force]
```

---

## VMware

### 1. Verify VMware Collections

```bash
ansible-galaxy collection list | grep vmware
```

### 2. Install VMware Collections

```bash
ansible-galaxy collection install \
    community.vmware vmware.vmware vmware.vmware_rest [--force]
```
