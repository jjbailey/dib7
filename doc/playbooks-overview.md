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
- **Provenance**: The build and conversion stages stamp their successful
  artifacts. Every import verifies the preceding stamp before it consumes an
  artifact, preventing a failed stage from publishing an older file left in
  `build_dir`.

### Phase 3: Cloud Import

- **AWS**: Uploads are handled via `import-ova-aws.yml`.
- **GCP**: Direct import of QCOW2 via `import-qcow2-gcp.yml`.
- **OpenStack**: Direct import of QCOW2 via `import-qcow2-openstack.yml`.
- **vSphere**: Deploy the `vSphere OVA` via `import-ova-vsphere.yml`, or
  create a `vSphere Template` via `import-ova-vsphere-template.yml`.

Every successful import also publishes its provider-specific artifact ID to
`catalogs/image-catalog.json`. See [image-catalog.md](image-catalog.md).

## Playbook Reference

### Core Infrastructure

- **`build-qcow2.yml`**: Builds QCOW2 image using diskimage-builder.
- **`convert-qcow2-to-ova.yml`**: Converts QCOW2 to OVA using qemu-img.

### Shared Task Files

Included with `include_tasks`, never run standalone. `ansible-playbook
--syntax-check` rejects them for that reason; it is not a defect.

- **`common-setup.yml`**: Provides variables for tasks.
- **`verify-stamp.yml`**: Refuses to consume an artifact the previous stage did
  not produce this run, and records the run that did produce it. See
  `local/pipeline-stamps.md` (internal-only, not part of the public dib7
  mirror).
- **`publish-image-catalog.yml`**: Writes one entry into the image catalog.
  Included by each import playbook after its import succeeds. See
  [image-catalog.md](image-catalog.md).

### Cloud Import / Publishing

- **`import-qcow2-gcp.yml`** (GCP): Uploads QCOW2 to GCS, registers as
  Compute Engine Image.
- **`import-qcow2-openstack.yml`** (OpenStack): Direct upload of QCOW2 to
  Glance as Image.
- **`import-ova-vsphere.yml`** (vSphere): Deploys OVA to vCenter content
  library. This is the `vSphere OVA` branch in the workflow diagram; the
  template playbook produces the `vSphere Template` branch.
- **`import-ova-vsphere-template.yml`** (vSphere): Deploys the OVA and converts
  it into a template in the `Templates` folder — the `vSphere Template` branch.
- **`import-ova-aws.yml`** (AWS): Imports OVA as AMI via VM Import/Export.

### Maintenance

- **`backfill-vsphere-ova-catalog.yml`**: Rebuilds `content_library_ova`
  catalog entries for OVAs an earlier run already imported, without contacting
  vCenter. Recovers entries lost to the publish bug fixed in this branch; not
  part of the normal pipeline.

## Usage Strategy

For a complete release pipeline, the playbooks should generally be executed in
the following order:

1. Run `build-qcow2.yml` to create the master artifact.

### Branching Logic

- **For GCP**: Run `import-qcow2-gcp.yml`.
- **For OpenStack**: Run `import-qcow2-openstack.yml`.
- **For vSphere**: Run `convert-qcow2-to-ova.yml` → `import-ova-vsphere.yml`
  if you want the `vSphere OVA` only.
- **For vSphere templates**: Run `convert-qcow2-to-ova.yml` →
  `import-ova-vsphere-template.yml` if you want a `vSphere Template`.
- **For AWS**: Run `convert-qcow2-to-ova.yml` → `import-ova-aws.yml`.
