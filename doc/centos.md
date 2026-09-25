# CentOS Stream 10

## CentOS Stream 10 cloud-image compatibility

CentOS changed the CentOS Stream 10 GenericCloud filename from
`CentOS-Stream-GenericCloud-x86_64-10-latest.x86_64.qcow2` to
`CentOS-Stream-GenericCloud-10-latest.x86_64.qcow2`. The pinned
`diskimage-builder` version can select the old name from the image index, so
the download step fails.

From the project root, apply the repository patch to the installed CentOS
element:

<!-- markdownlint-disable MD013 -->

```bash
DIB7_SITE=$(~/.dib7/bin/python3 -c "import site; print(site.getsitepackages()[0])")
patch -b -d "$DIB7_SITE/diskimage_builder/elements/centos/root.d" \
      < patches/diskimage-builder-centos10-generic-image.patch
```

<!-- markdownlint-enable MD013 -->

The patch changes only the `10-stream` filename matcher. Other CentOS
releases retain the existing matcher, and the patch is inert for Fedora,
Debian, Ubuntu, and Rocky builds sharing the virtualenv.

## Verifying the patch is in effect

Confirm that the live virtualenv contains the patched element:

```bash
DIB7_SITE=$(~/.dib7/bin/python3 -c "import site; print(site.getsitepackages()[0])")
grep -c 'CentOS-Stream-GenericCloud-10-' \
  "$DIB7_SITE/diskimage_builder/elements/centos/root.d/10-centos-cloud-image"
# expect: 1
```

The patch edits an installed package file, so installing or upgrading
`diskimage-builder` can silently replace it. Reapply the patch after an
upgrade, unless the installed upstream element already contains the new
CentOS 10 filename matcher.
