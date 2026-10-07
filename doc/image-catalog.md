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
Each entry is identified by `(logical_name, provider, artifact_type, version,
project, region, scope)`. For superseding providers, `version` is omitted
from replacement matching; project/region/scope remain part of the identity so
separate cloud projects, regions, and vCenters cannot evict one another.
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
  "ssh_username": "ubuntu",
  "status": "published",
  "region": "us-west-2"
}
```

`ssh_username` records the default non-root login configured in the image.
Deployment tools can use it to report the login name without inferring it from
the image name. Provider credentials, key pairs, and other launch settings
remain deployment-side configuration.

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
which drops `version` from the match while retaining project, region, and
scope, so a new entry replaces every version of that artifact in the same
target scope.

The practical rule for consumers: **for `gcp`, `openstack`, and `vsphere` there
is exactly one current row per image, artifact type, and target scope.** Version pinning is only meaningful for `aws`.

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

Conversion and import stages invoked without `-e run_id=...` preserve the run
recorded in the preceding artifact's stamp. When an explicit `run_id` is also
present, stamp verification requires them to agree. A build invoked without a
run ID writes `manual`, which subsequent stages preserve even though they
verify the stamp. Legacy conversion stamps may also contain `manual`; rerun
conversion to inherit the build stamp's ID. Use one explicit run ID from the
build onward for release versioning; `manual` does not identify a unique build.

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

Each reconciler works on one target scope and auto-selects it when the catalog
holds exactly one; when the catalog holds several targets for a provider, the
script fails and names the flag to disambiguate:

- **AWS** groups AMI checks by region and supports `--region` and `--profile`.
  The scope is the account, selected with `--project` (`--account-id` is an
  alias) when the catalog contains rows for more than one AWS account.
- **GCP** checks image self-links and infers the project when the catalog
  contains one; use `--project` or `--credentials-file` when needed. The
  resolved credentials must belong to the selected project, and the script
  fails with both project IDs when they disagree.
- **OpenStack** checks Glance image IDs through the selected clouds.yaml entry
  and supports `--cloud`, `--project-id`, and `--region-name`. It requires
  `--project-id` when the catalog holds several OpenStack projects and
  `--region-name` when it holds several regions, and it verifies the
  authenticated project against the selection before touching anything. A row
  recorded for a different region is left alone. A row with no region predates
  the field and is still checked.
- **vSphere** checks content-library items and templates through
  `pwsh`/PowerCLI, which requires `vcenter_hostname`, `vcenter_username`, and
  `vcenter_password` in the environment. It selects the content library
  automatically when the catalog holds one (`--library` otherwise). Pass
  `--vcenter` when the catalog holds several vCenters, or when some rows name a
  vCenter and others do not. A row with no `scope.vcenter` is not treated as
  every vCenter. Removal deletes the exact row that was checked, not every row
  that shares its artifact name.

All four scripts accept `--force` when more than half of the active provider
rows in the selected scope would be removed. Successful reconciliation exits
zero, including when rows were removed; errors exit nonzero. `tests/validate.sh` checks syntax
and catalog shape, but deliberately does not perform live cloud calls.

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
