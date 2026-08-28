# Workflow

<!-- markdownlint-disable MD013 -->

```mermaid
flowchart TB
    DIB["diskimage-builder"] --> QCOW2["💽 qcow2"]
    QCOW2 --> VMDK["📦 vmdk"]
    VMDK --> OVF["📄 ovf"]
    OVF --> OVA["📦 ova"]
    QCOW2 --> GCS["🪣 GCS Bucket"]
    GCS --> GCP_IMG["☁️ GCP Image"]
    QCOW2 --> OPENSTACK_IMG["☁️ OpenStack Image"]
    OVA --> S3["🪣 S3 Bucket"]
    S3 --> AWS_IMG["☁️ AWS AMI"]
    OVA --> VSPHERE_IMG["☁️ vSphere OVA"]
    VSPHERE_IMG --> VSPHERE_TPL["☁️ vSphere Template"]
    AWS_IMG --> CATALOG["🗂️ Versioned image catalog"]
    GCP_IMG --> CATALOG
    OPENSTACK_IMG --> CATALOG
    VSPHERE_IMG --> CATALOG
    VSPHERE_TPL --> CATALOG
```

Each import writes its provider artifact ID to
`catalogs/image-catalog.json`. The build and conversion stages write provenance
stamps alongside their artifacts; downstream stages require those stamps before
they consume a QCOW2 or OVA. See `local/pipeline-stamps.md` (internal-only,
not part of the public dib7 mirror) and [image-catalog.md](image-catalog.md).
