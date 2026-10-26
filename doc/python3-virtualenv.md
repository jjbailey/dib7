# Python 3 Virtual Environment for diskimage-builder

DIB7 runs from a single Python virtual environment at `~/.dib7`. It holds
`ansible-core`, `diskimage-builder`, and the controller-side cloud SDKs, and it
builds every distro — Debian, Ubuntu, Fedora, CentOS, and Rocky alike.

Fedora needs a patched `diskimage-builder` element. That patch is applied inside
`~/.dib7` along with everything else: it only touches the `fedora` element, so
it has no effect on the other builds. See [fedora.md](fedora.md).

All five inventory groups point at this one environment through `venv_bin` in
`group_vars/all/main.yml`. See [group-vars-all.md](group-vars-all.md).

## 1. Install Required System Packages

The pinned `ansible-core` (2.18.18) requires Python 3.11 or newer on the
control node, so check the interpreter version before creating the venv.

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
python3 --version   # must report 3.11 or newer
```

## 2. Create the Virtual Environment

```bash
python3 -m venv ~/.dib7
```

## 3. Upgrade pip and Core Build Tools

```bash
~/.dib7/bin/python3 -m pip install --upgrade pip setuptools wheel
```

## 4. Install Project Python Dependencies

Run these from the project root:

```bash
~/.dib7/bin/python3 -m pip install -r requirements.txt
```

This installs `diskimage-builder`, `ansible-core`, `PyYAML`, and the
controller-side cloud SDKs used by the project playbooks.

Then install the pinned Galaxy collections:

```bash
~/.dib7/bin/ansible-galaxy collection install -r requirements.yml
```

The Azure collection is staged and is not part of this install. Its SDK
dependencies stay in the collection's own `requirements.txt` and are installed
when that pipeline lands. See [azure.md](azure.md).

Invoke pip as `~/.dib7/bin/python3 -m pip`, not `~/.dib7/bin/pip`. The
interpreter path is what activates the venv and fixes the shebangs written into
the installed console scripts. Calling a `pip` wrapper directly installs under
whichever interpreter that wrapper's own shebang names, which can quietly place
packages outside the venv.

## 5. Apply the DIB Compatibility Patches

Apply the matching patch when building Fedora 43+ or CentOS Stream 10, unless
the installed upstream element already contains that release's filename fix.
Each patch changes only its own distro element and is harmless to the other
builds sharing the venv.

From the project root:

<!-- markdownlint-disable MD013 -->

```bash
DIB7_SITE=$(~/.dib7/bin/python3 -c "import site; print(site.getsitepackages()[0])")
patch -b -d "$DIB7_SITE/diskimage_builder/elements/fedora/root.d" \
      < patches/diskimage-builder-fedora-generic-image.patch
```

<!-- markdownlint-enable MD013 -->

See [fedora.md](fedora.md) for what the Fedora patch does and how to verify it.

CentOS Stream 10 builds also require the CentOS filename patch:

```bash
patch -b -d "$DIB7_SITE/diskimage_builder/elements/centos/root.d" \
      < patches/diskimage-builder-centos10-generic-image.patch
```

It is specific to `10-stream` and harmless for other CentOS releases. See
[centos.md](centos.md) for what it changes and how to verify it. Reapply it
after upgrading `diskimage-builder` unless the installed element includes the
upstream fix.

## 6. Verify Installation

```bash
~/.dib7/bin/ansible --version              # expect ansible-core 2.18.18
~/.dib7/bin/disk-image-create --version    # expect 3.43.0
```

Confirm the venv resolves its own packages:

```bash
~/.dib7/bin/python3 -c 'import diskimage_builder as d; print(d.__file__)'
# expect a path under ~/.dib7
```

If that prints somewhere unexpected, the environment is importing from outside
itself. Recreate it per sections 2-4 rather than copying an existing venv into
place: a copy carries the original interpreter paths across verbatim, so the
copy silently keeps running whatever the original resolved.

## 7. Install Additional Build Dependencies (Important)

```bash
sudo apt install -y qemu-utils kpartx debootstrap \
    parted dosfstools gdisk squashfs-tools libguestfs-tools lvm2
```

## 8. Test a Simple Image Build

```bash
export DIB_RELEASE=noble
~/.dib7/bin/disk-image-create ubuntu vm -o ubuntu-test
```

## Using the Environment

The playbooks do not need the venv activated. `group_vars/all/main.yml` sets
`venv_bin` to `~/.dib7/bin` and prepends it to `PATH` for the build tasks, so
`disk-image-create` resolves correctly during a run.

To use the tools interactively, either call them by full path as above, or
activate the venv:

```bash
source ~/.dib7/bin/activate
```

## Upgrading

`requirements.txt` pins `ansible-core` and `diskimage-builder`. After changing a
pin, reinstall, re-apply the Fedora and/or CentOS patch if needed, and
re-verify:

```bash
~/.dib7/bin/python3 -m pip install -r requirements.txt
```

A `diskimage-builder` upgrade can overwrite either patched element. Re-run
`tests/validate.sh`; if it reports a missing upstream fix, apply the matching
patch from section 5 and verify again.
