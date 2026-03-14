# DIB7 Playbooks Overview

## Executive Summary

The `dib7/playbooks` directory contains automation logic for the Disk Image
Builder (DIB7) project.

The primary objective is to facilitate the lifecycle of virtual machine disk
images, including:

- Building base images (QCOW2)
- Converting images to platform-specific formats (OVA, VMDK)
- Importing/publishing images to cloud providers (AWS, GCP, OpenStack, VMware vSphere)

## Workflow Pipeline

The playbooks are designed to be executed in a pipeline, moving from a raw
build to a cloud-ready artifact.

### Phase 1: Preparation & Build

- **Build**: `build-qcow2.yml` generates master QCOW2 artifact (includes `common-setup.yml`).

### Phase 2: Conversion (Format Transformation)

- **Transformation**: `convert-qcow2-to-ova.yml` converts master QCOW2 to OVA
  for vSphere/AWS.
- **(Implicit)**: Some playbooks assume VMDK from build/conversion.

### Phase 3: Cloud Import

- **AWS**: Uploads are handled via `import-ova-aws.yml`.
- **GCP**: Direct import of QCOW2 via `import-qcow2-gcp.yml`.
- **OpenStack**: Direct import of QCOW2 via `import-qcow2-openstack.yml`.
- **vSphere**: Deployment of OVA via `import-ova-vsphere.yml`.

## Playbook Reference

### Core Infrastructure

- **`common-setup.yml`**: Provides variables for tasks (included playbook, not standalone).
- **`build-qcow2.yml`**: Builds QCOW2 image using diskimage-builder.
- **`convert-qcow2-to-ova.yml`**: Converts QCOW2 to OVA using qemu-img.

### Cloud Import / Publishing

- **`import-qcow2-gcp.yml`** (GCP): Uploads QCOW2 to GCS, registers as
  Compute Engine Image.
- **`import-qcow2-openstack.yml`** (OpenStack): Direct upload of QCOW2 to
  Glance as Image.
- **`import-ova-vsphere.yml`** (vSphere): Deploys OVA to vCenter.
- **`import-ova-aws.yml`** (AWS): Imports OVA as AMI via VM Import/Export.

## Usage Strategy

For a complete release pipeline, the playbooks should generally be executed in
the following order:

1. Run `build-qcow2.yml` to create the master artifact.

### Branching Logic

- **For GCP**: Run `import-qcow2-gcp.yml`.
- **For OpenStack**: Run `import-qcow2-openstack.yml`.
- **For vSphere**: Run `convert-qcow2-to-ova.yml` → `import-ova-vsphere.yml`.
- **For AWS**: Run `convert-qcow2-to-ova.yml` → `import-ova-aws.yml`.
