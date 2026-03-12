# Installing diskimage-builder with Python 3 Virtual Environment

## 1. Install Required System Packages

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
```

## 2. Create a Working Directory

```bash
mkdir -p ~/venvs/diskimage-builder
cd ~/venvs/diskimage-builder
```

## 3. Create the Virtual Environment

```bash
python3 -m venv venv
```

## 4. Activate the Virtual Environment

```bash
source venv/bin/activate
```

## 5. Upgrade pip and Core Build Tools

```bash
pip install --upgrade pip setuptools wheel
pip install google-auth google-api-python-client google-cloud-storage
```

## 6. Install diskimage-builder

```bash
pip install diskimage-builder
```

## 7. Verify Installation

```bash
disk-image-create --version
```

## 8. Install Additional Build Dependencies (Important)

```bash
sudo apt install -y qemu-utils kpartx debootstrap \
    parted dosfstools gdisk squashfs-tools
```

## 9. Test a Simple Image Build

```bash
export DIB_RELEASE=noble
disk-image-create ubuntu vm -o ubuntu-test
```
