# Install Google Cloud CLI (`gcloud`) on Ubuntu

## 1. Install Dependencies

```bash
sudo apt update
sudo apt install -y apt-transport-https ca-certificates gnupg curl
```

## 2. Add Google Cloud Public Key

```bash
curl https://packages.cloud.google.com/apt/doc/apt-key.gpg |
    sudo gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg
```

## 3. Add Cloud SDK Repository

```bash
echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] \
https://packages.cloud.google.com/apt cloud-sdk main" |
    sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list
```

## 4. Install Google Cloud CLI

```bash
sudo apt update
sudo apt install -y google-cloud-cli
```

## 5. Verify Installation

```bash
gcloud version
```

## 6. Initialize gcloud

```bash
gcloud init
```

## Optional Components

```bash
gcloud components install kubectl beta
sudo apt install google-cloud-cli-gke-gcloud-auth-plugin
```
