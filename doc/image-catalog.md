# Image catalog contract

DIB7 produces images; the deployment project consumes them. The import
playbooks publish a machine-readable JSON catalog at `image_catalog_path`
(default: `catalogs/image-catalog.json` in the repo) after a successful provider
import. The catalog is an output artifact, not an Ansible inventory. It lives in
the repo rather than in `build_dir` so it survives a wipe of the build tree, and
it is committed here, which is what gives it history and a backup. It can
contain site-specific identifiers, so do not publish it when synchronizing a
public source tree.

The schema is [catalogs/image-catalog.schema.json](../catalogs/image-catalog.schema.json).
Each entry is identified by `(logical_name, provider, artifact_type, version)`.
Re-publishing that same tuple replaces the entry atomically. Whether older
versions survive alongside the new one is a per-provider policy described
below. A small lock file prevents concurrent publishers from losing entries.

`artifact_type` is part of the identity because one image can reach a provider
as more than one kind of artifact. A vSphere run publishes both the content
library OVA and the template cloned from it; a provider that later grows a
second artifact kind - an AMI alongside a snapshot, say - needs the same room.
The consequence for consumers is that resolving a logical name for a provider
can return more than one row, so **filter on `artifact_type` before pinning a
version**. Terraform cloning a vSphere VM wants `content_library_template`;
something staging an OVA elsewhere wants `content_library_ova`.

Example entry:

```json
{
  "logical_name": "ubuntu24045-base",
  "provider": "aws",
  "artifact_id": "ami-0a6f5113e545a1f52",
  "artifact_type": "ami",
  "version": "1786293956",
  "architecture": "amd64",
  "boot_mode": "uefi",
  "source_build": "ubuntu24045-base",
  "status": "published",
  "region": "us-west-2"
}
```

Whether older versions survive depends on the provider, and the test is whether
a new run destroys what the older rows point at:

<!-- markdownlint-disable MD013 -->

| provider    | what a new run does to the previous artifact                                                       | catalog policy      |
| ----------- | -------------------------------------------------------------------------------------------------- | ------------------- |
| `aws`       | nothing; a new AMI id is minted and the old AMI persists                                           | versions accumulate |
| `gcp`       | image deleted and recreated under the same name, so the selfLink is stable and its content changes | supersedes          |
| `openstack` | image deleted by name; the old UUID stops resolving even though each upload mints a new one        | supersedes          |
| `vsphere`   | content library item and template are named for the image and overwritten in place                 | supersedes          |

<!-- markdownlint-enable MD013 -->

Note that a unique-looking `artifact_id` is not the test - OpenStack mints a
fresh UUID every upload and still supersedes, because the previous image is
deleted. The publishers for the three superseding providers pass `--supersede`,
which drops `version` from the match so a new entry replaces every version of
that artifact.

The practical rule for consumers: **for `gcp`, `openstack`, and `vsphere` there
is exactly one row per image per `artifact_type`, and it is always current
state.** Version pinning is only meaningful for `aws`.

A publisher only ever rewrites rows matching its own `provider`, so entries for
other providers are left untouched. That is what makes it safe to re-run one
provider's import, or `backfill-vsphere-ova-catalog.yml`, against a catalog
holding entries an operator maintains by other means.

`version` is the run id, passed to every stage as `-e run_id=...` by whatever
driver invokes the pipeline. The convention is Unix epoch seconds stamped once
when the run begins, so every image built and imported by that run shares a
version - which is what lets a deployment pin a whole run's artifacts as a set
rather than image by image. Epoch seconds also sort correctly as strings, so
"newest version of this image" is a plain lexicographic comparison.

A stage invoked directly, with no `-e run_id=...`, still records a real version.
Each import verifies the stage stamp written beside the artifact before
consuming it, and falls back to the run id recorded in that stamp. The two
agree whenever both are present, because verifying the stamp is precisely what
fails a stage handed an artifact from a different run. The literal version
`manual` therefore only appears when an entry is published without verifying
any stamp - which no import playbook does - so treat it as a defect to correct
rather than a value to pin.

Provider-specific identifiers are recorded directly: AWS AMI IDs, GCP image
self-links, OpenStack Glance image IDs, and vSphere content-library names.
Additional scope fields identify a GCP project or vSphere content library where
needed. Terraform should resolve a logical name for convenience rather than
hardcoding an artifact id.

How to pin depends on the provider, and follows from the table above. For
`aws`, pin `version` or the AMI id: both are stable, and older entries stay in
the catalog. For `gcp`, `openstack` and `vsphere` there is nothing durable to
pin - the single row is current state by construction, and the artifact behind
it is replaced by the next run - so a deployment that must not move underneath
itself has to capture the catalog at release time instead of resolving it live.

## Catalog reconciliation

The provider reconcilers compare published catalog rows with live cloud state
and remove stale rows entirely. They also remove rows already marked `retired`,
so the catalog does not accumulate historical tombstones. Each script reads a
snapshot without holding the lock during cloud calls, then re-reads the catalog
under an exclusive lock before an atomic replacement.

```bash
bin/reconcile-catalog-aws.py --dry-run
bin/reconcile-catalog-gcp.py --dry-run
bin/reconcile-catalog-openstack.py --dry-run
```

AWS groups AMI checks by region and supports `--region` and `--profile`. GCP
checks image self-links and infers the project when the catalog contains one;
use `--project` or `--credentials-file` when needed. OpenStack checks Glance
image IDs through the selected clouds.yaml entry and supports `--cloud` and
`--project-id`. All three scripts accept `--force` when more than half of the
active provider rows would be removed. `tests/validate.sh` checks syntax and
catalog shape, but deliberately does not perform live cloud calls.

### OpenStack credentials

Before connecting, `reconcile-catalog-openstack.py` checks for the credentials
needed by the OpenStack SDK. With password authentication, export these
variables (project ID may be used instead of project name):

```bash
export OS_AUTH_URL=https://keystone.example.com:5000/v3
export OS_USERNAME=my-username
export OS_PASSWORD=...
export OS_PROJECT_NAME=my-project
# Or use OS_PROJECT_ID instead of OS_PROJECT_NAME.
```

`OS_USER_ID` may be used instead of `OS_USERNAME`, and `OS_TOKEN` instead of
`OS_PASSWORD` when using token authentication. If credentials are stored in a
`clouds.yaml` entry, pass its name with `--cloud <name>` or set `OS_CLOUD`
instead; those modes do not require the individual `OS_*` variables. Missing
credentials are reported before any OpenStack connection is attempted.

## Release capture

That is what makes the release step load-bearing rather than optional: a
release process can commit the generated file to a catalog repository or copy
it to object storage, and for the superseding providers that copy is the only
immutable record of what a given release deployed. Set `image_catalog_path`
accordingly; credentials remain external to this contract and are configured
independently by each project.
