# Vaults Required by the Playbooks

## Editing a Vault

`bin/aws-vault.sh`, `bin/gcp-vault.sh`, `bin/openstack-vault.sh`, and
`bin/vsphere-vault.sh` wrap `ansible-vault edit`/`create
--encrypt-vault-id=default` against the matching file below, creating it if it
doesn't exist yet:

```sh
bin/aws-vault.sh
```

Set `VAULT` to point at a different file (e.g. a per-environment vault):

```sh
VAULT=vaults/aws-staging.yml bin/aws-vault.sh
```

## AWS Vault

vaults/aws.yml

```txt
aws_region: "my-region"
s3_bucket: "my-bucket"
vmimport_role_name: "vmimport-role"
```

## GCP Vault

vaults/gcp.yml

```txt
gcp_project: "my-project"
gcs_bucket: "my-bucket"
gcp_import_location: "us-central1"

service_account_key: |
  {
    "type": "service_account",
    "project_id": "my-project",
    "private_key_id": "my-private-key-id",
    "private_key": "-----BEGIN PRIVATE KEY-----
     ..."
    "client_email": you@...iam.gserviceaccount.com",
    "client_id": "my-client-id",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/...iam.gserviceaccount.com",
    "universe_domain": "googleapis.com"
  }

service_account_contents: "{{ service_account_key }}"
```

### `gcp_import_location`

The region the Migrate to Virtual Machines _import job_ runs in - the value
passed to `gcloud migration vms image-imports --location`. It is easy to
misread this as a storage setting, so, concretely, it does **not** control:

- **Where `gcs_bucket` lives.** A bucket's location is fixed when the bucket
  is created and is not settable from here. The import reads the staged QCOW2
  across regions perfectly well when the two differ.
- **Where the finished image lives.** A GCE Compute image is a _global_
  resource, so the imported image is equally usable from every region no
  matter which one converted it.

So this is purely a choice of which region does the conversion work, and it
can be changed freely - including to route around a regional outage:

```sh
ansible-playbook playbooks/import-qcow2-gcp.yml -e gcp_import_location=us-east1
```

On 2026-08-12 the import service in `us-central1` failed four consecutive
times at the `loadingSourceFiles` step with `code 13`, "Internal migration
service error", while the byte-identical staged object imported cleanly in
`us-east1`. If an import fails with an internal error and no useful detail,
retrying in another region is the fastest way to tell a bad artifact apart
from a bad region.

## OpenStack Vault

vaults/openstack.yml

```txt
openstack_auth:
  auth_url: "https://keystone.example.com:5000/v3"
  username: "my-username"
  password: "my-password"
  project_name: "my-project"
  user_domain_name: "Default"
  project_domain_name: "Default"
  # region_name: "my-region"  # only needed for multi-region clouds
```

`region_name` is optional and only required for multi-region clouds; omit it
for single-region clouds. When set, it is also recorded as `region` on the
image's catalog entry.

## vSphere Vault

`vaults/vsphere.yml`

```txt
vcenter_hostname: "my-vcenter"
vcenter_username: "my-admin-user"
vcenter_password: "my-admin-password"
vsphere_content_library: "my-content-library"
vsphere_template_name: "inventory-item-base.tmpl"
```

`vsphere_content_library` is used by `import-ova-vsphere.yml` to create the
`vSphere OVA`, and `vsphere_template_name` is used by
`import-ova-vsphere-template.yml` to create the `vSphere Template`.
