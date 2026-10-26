# Azure (staged)

Azure is on the roadmap and is not part of a build or import yet. What is
already in the tree, so the pipeline does not have to invent its credential
path later:

- `vaults/azure.yml`, encrypted and unused by every current playbook
- `bin/azure-vault.sh`, a symlink to `bin/edit-vault.sh`

Do not install `azure.azcollection` or the Azure CLI for the workflows that
ship today. `requirements.yml` keeps the 4.1.0 pin commented out because
`tests/validate.sh` requires every pin it lists. Restore that pin when the
first Azure playbook lands, then follow the install below.

## Ansible collection and Python dependencies

When the pipeline lands, install the collection with the other pins and then
its own SDK requirements into the same virtual environment Ansible uses:

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

Install Azure CLI as an operating-system package, outside the `~/.dib7` Python
virtual environment. The commands below follow Microsoft's APT repository
instructions:

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
