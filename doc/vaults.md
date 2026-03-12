# Vaults Required by the Playbooks

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
gcs_location: "my-location"

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
```

## vSphere Vault

vaults/vsphere.yml

```txt
vcenter_hostname: "my-vcenter"
vcenter_username: "my-admin-user"
vcenter_password: "my-admin-password"
vsphere_content_library: "my-content-library"
```
