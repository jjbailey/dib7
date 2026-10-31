# Azure

`playbooks/import-qcow2-azure.yml` imports the QCOW2 from `build-qcow2.yml`
as an Azure **managed image**:

1. `qemu-img` converts the QCOW2 to a fixed-format VHD in `build_dir`. That
   is the only disk format Azure accepts. The file is written sparse, so its
   apparent size is the full virtual disk (35 GiB plus a 512-byte footer) but
   it only uses as much space as the QCOW2 holds. The conversion goes through a
   temporary file, and the VHD is always deleted when the play ends, whether
   it succeeded or not.
2. The staging storage account is created if it does not exist yet
   (Standard_LRS, StorageV2, HTTPS-only, TLS 1.2, no public blob access,
   tagged `managed_by: dib7`). The blob container is also created if missing.
   An existing account is used as it is; the playbook never changes its
   settings. It must be in the project's `location`, because Azure only
   creates an image from a VHD in the same region; the playbook checks this
   before uploading.
3. The VHD is always uploaded as a page blob, replacing any blob with the same
   name, so a blob from an earlier build is never reused. All-zero pages are
   skipped, so only the used blocks go over the network.
4. A managed image with the same name in the resource group is deleted and
   created again by default (`azure_replace_existing_image: true`). Its
   Hyper-V generation follows `image_boot_mode`: `uefi` gives `V2` (Gen2).
5. Once the image exists, the staged blob is deleted
   (`azure_delete_vhd_after_import: true`). A managed image keeps its own
   copy of the disk.
6. One catalog row is published: provider `azure`, artifact type
   `managed_image`, `artifact_id` set to the image's resource ID, `project` set
   to the subscription ID, `region` set to the location, and
   `scope.resource_group`. Azure **supersedes**, as GCP does: the resource ID
   is derived from the name, so it stays the same while the content changes.

```bash
~/.dib7/bin/ansible-playbook playbooks/import-qcow2-azure.yml \
  -e "run_id=$RUN_ID" -l <host-or-group> --vault-password-file ~/.ssh/dib-vault-pass
# or, consuming an existing build:
LIMIT=ubuntu26041 local/test-azure.sh
```

Select a subscription with `-e azure_target_project=<vault-key-or-subscription-id>`
(`AZURE_TARGET_PROJECT` for the `local/` wrappers). If the vault holds a
single entry, it is selected automatically.

### Credentials

The service principal from the vault is passed to every `azure.azcollection`
module through `module_defaults` (`azure_module_defaults`, built by
`playbooks/tasks/select-azure-project.yml`). It is deliberately **not** passed
through `environment:` the way AWS uses `aws_task_env`. Ansible starts each
module as `sh -c 'VAR=... python ...'`, so an environment-borne secret can be
read by anyone running `ps` for as long as the multi-GB upload takes. Because
the credentials are explicit parameters, the modules also never fall back to
`~/.azure/credentials` or a logged-in `az` session.

The principal needs permission to create storage accounts and images in the
resource group (for example, Contributor on the resource group or the
subscription). The resource group must already exist.

### Variables

| Variable                        | Default                               | Description                                                       |
| ------------------------------- | ------------------------------------- | ----------------------------------------------------------------- |
| `azure_storage_container`       | `dib7-images`                         | Blob container for the staged VHD. A vault entry can override it. |
| `azure_replace_existing_image`  | `true`                                | Delete and recreate a same-named image rather than failing.       |
| `azure_delete_vhd_after_import` | `true`                                | Remove the staged VHD blob after the image is created.            |
| `azure_hyper_v_generation`      | `V2` when `image_boot_mode` is `uefi` | Hyper-V generation recorded on the image.                         |
| `vhd_file`                      | `{{ image_name }}.vhd`                | Local and blob name of the converted disk.                        |

Azure rejects a VHD whose virtual size is not a whole number of MiB, and it
only does so at image-creation time, after the upload. The playbook checks
the size before converting. `image_size` is set in GiB, so every current build
passes this check.

### Reconciliation

```bash
~/.dib7/bin/python3 bin/reconcile-catalog-azure.py --dry-run
```

This works like the GCP reconciler. It selects the subscription automatically
when the catalog holds only one; otherwise pass `--subscription` (alias
`--project`). It removes rows whose managed image no longer exists, and rows
already marked `retired`. It reads `AZURE_TENANT`/`AZURE_TENANT_ID`,
`AZURE_CLIENT_ID`, and `AZURE_SECRET`/`AZURE_CLIENT_SECRET`, and falls back to
`DefaultAzureCredential` (`az login`, managed identity).

## Ansible collection and Python dependencies

Install the collection with the other pins, then install its own SDK
requirements into the same virtual environment Ansible uses:

```bash
~/.dib7/bin/ansible-galaxy collection install -r requirements.yml
```

The collection's Python SDK dependencies are maintained in its own
`requirements.txt`. Install them into the same virtual environment used by
Ansible:

```bash
~/.dib7/bin/python3 -m pip install -r \
  ~/.ansible/collections/ansible_collections/azure/azcollection/requirements.txt
```

That is separate from the repository's root `requirements.txt`, which contains
the core DIB tools and the controller-side SDK requirements used by the
existing AWS, GCP, and OpenStack playbooks. If Ansible Galaxy is configured to
install collections in a different directory, use the installed collection's
`requirements.txt` at that location.

The Azure collection requires Python 3.10 or newer and ansible-core 2.16 or
newer; DIB7's shared environment uses Python 3.11+ and ansible-core 2.18.18.
See the [Azure collection installation instructions](https://github.com/ansible-collections/azure#installation)
and [Ansible Galaxy collection page](https://galaxy.ansible.com/ui/repo/published/azure/azcollection/).

## Azure CLI on Ubuntu

The pipeline does not use the Azure CLI. It is useful for inspecting what the
pipeline created by hand. Install it as an operating-system package, outside
the `~/.dib7` Python virtual environment. The commands below follow
Microsoft's APT repository instructions:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl apt-transport-https gnupg lsb-release

sudo mkdir -p /etc/apt/keyrings
curl -sLS https://packages.microsoft.com/keys/microsoft.asc |
  gpg --dearmor | sudo tee /etc/apt/keyrings/microsoft.gpg > /dev/null
sudo chmod go+r /etc/apt/keyrings/microsoft.gpg

AZ_DIST=$(lsb_release -cs)
echo "Types: deb
URIs: https://packages.microsoft.com/repos/azure-cli/
Suites: ${AZ_DIST}
Components: main
Architectures: $(dpkg --print-architecture)
Signed-by: /etc/apt/keyrings/microsoft.gpg" |
  sudo tee /etc/apt/sources.list.d/azure-cli.sources

sudo apt-get update
sudo apt-get install -y azure-cli
```

Verify the install:

```bash
az version
```

When you need an interactive local Azure CLI session, sign in and check which
subscription is active:

```bash
az login
az account show
```

If you have access to more than one subscription, select the one for your
local work with `az account set --subscription <subscription-id>`. See
[Sign in with Azure CLI](https://learn.microsoft.com/en-us/cli/azure/authenticate-azure-cli?view=azure-cli-latest)
for other authentication methods and subscription management details.

Microsoft maintains current distribution support and installation options in
[Install the Azure CLI on Linux](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli-linux?view=azure-cli-latest).
The CLI is installed separately from Python packages; do not add `azure-cli`
to the repository's `requirements.txt`.
