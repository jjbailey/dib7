# Fedora Server 43+

---

## Patch required to build Fedora Server 43+

Fedora changed the naming convention for the cloud image downloads at release
43: the file is now `Fedora-Cloud-Base-Generic-<release>-<subrelease>.<arch>.qcow2`
rather than `Fedora-Cloud-Base-<release>-...`. Stock `diskimage-builder` 3.42.0
only knows the older name, so the download step fails to resolve an image.

The patch is kept in the repo and applies to the `fedora` element inside the
`~/.dib7` venv:

From the project root:

<!-- markdownlint-disable MD013 -->

```bash
DIB7_SITE=$(~/.dib7/bin/python3 -c "import site; print(site.getsitepackages()[0])")
patch -b -d "$DIB7_SITE/diskimage_builder/elements/fedora/root.d" \
      < patches/diskimage-builder-3.42.0-fedora-generic-image.patch
```

<!-- markdownlint-enable MD013 -->

It edits only `elements/fedora/root.d/10-fedora-cloud-image`, which no other
distro reads, so it is inert for the Debian, Ubuntu, CentOS, and Rocky builds that
share the same venv.

The patch content, for reference:

<!-- markdownlint-disable MD013 MD010 -->

```diff
--- 10-fedora-cloud-image~	2026-05-16 18:59:13.544979462 -0700
+++ 10-fedora-cloud-image	2026-05-16 19:01:12.385447740 -0700
@@ -53,9 +53,20 @@
     esac
     # We have curl write headers to stderr so that we can debug fedora
     # mirror locations that don't have valid subreleases in their paths.
+
+# Fedora 43+ uses "Generic" cloud image naming
+if [ "${DIB_RELEASE}" -ge 43 ] 2>/dev/null; then
+    SUBRELEASE_REGEXP=${SUBRELEASE_REGEXP:-'(?<=Fedora-Cloud-Base-Generic-'${DIB_RELEASE}'-).*?(?=.'${ARCH}'.qcow2)'}
+    SUBRELEASE=$(head -1 < <(curl -Lis -D /dev/stderr $DIB_CLOUD_IMAGES/ | grep -o -P $SUBRELEASE_REGEXP | sort -r))
+    BASE_IMAGE_FILE=${BASE_IMAGE_FILE:-Fedora-Cloud-Base-Generic-$DIB_RELEASE-$SUBRELEASE.$ARCH.qcow2}
+else
     SUBRELEASE_REGEXP=${SUBRELEASE_REGEXP:-'(?<=Fedora-Cloud-Base-'${DIB_RELEASE}'-).*?(?=.'${ARCH}'.qcow2)'}
     SUBRELEASE=$(head -1 < <(curl -Lis -D /dev/stderr $DIB_CLOUD_IMAGES/ | grep -o -P $SUBRELEASE_REGEXP | sort -r))
     BASE_IMAGE_FILE=${BASE_IMAGE_FILE:-Fedora-Cloud-Base-$DIB_RELEASE-$SUBRELEASE.$ARCH.qcow2}
+fi
+
+    SUBRELEASE=$(head -1 < <(curl -Lis -D /dev/stderr $DIB_CLOUD_IMAGES/ | grep -o -P $SUBRELEASE_REGEXP | sort -r))
+    BASE_IMAGE_FILE=${BASE_IMAGE_FILE:-Fedora-Cloud-Base-$DIB_RELEASE-$SUBRELEASE.$ARCH.qcow2}
     BASE_IMAGE_TAR=Fedora-Cloud-Base-$DIB_RELEASE-$SUBRELEASE.$ARCH.tgz
     IMAGE_LOCATION=$DIB_CLOUD_IMAGES/$BASE_IMAGE_FILE
     CACHED_IMAGE=$DIB_IMAGE_CACHE/$BASE_IMAGE_FILE
```

<!-- markdownlint-enable MD013 MD010 -->

The two re-assignments after `fi` are carried over from the original and are
redundant: `SUBRELEASE` recomputes to the same value, and `BASE_IMAGE_FILE`
uses `${BASE_IMAGE_FILE:-...}`, so the `Generic` name set inside the branch is
preserved. They are harmless, but do not mistake them for the branch failing to
take effect.

`-b` saves the pre-patch original as `10-fedora-cloud-image.orig`, which is
handy for confirming what changed. Without it `patch` leaves no backup.

## Verifying the patch is in effect

Applying the patch is not sufficient on its own — it only matters if the
`disk-image-create` that runs actually loads the element from `~/.dib7`.
Confirm both:

```bash
# 1. Which diskimage_builder does the venv resolve?
~/.dib7/bin/python3 -c 'import diskimage_builder as d; print(d.__file__)'
# expect a path under ~/.dib7

# 2. Is the branch present in the element that will be read?
DIB7_SITE=$(~/.dib7/bin/python3 -c "import site; print(site.getsitepackages()[0])")
grep -c "Fedora-Cloud-Base-Generic" "$DIB7_SITE/diskimage_builder/elements/fedora/root.d/10-fedora-cloud-image"
# expect: 2
```

Check 1 tells you which install is live; check 2 tells you whether that install
is patched. Both must pass — a patched element in a copy that never gets
imported is exactly as broken as no patch at all. If check 1 points somewhere
unexpected, see [python3-virtualenv.md](python3-virtualenv.md).

Version output cannot distinguish a patched from an unpatched install: both
report `diskimage-builder` 3.42.0. Use the `grep -c` check above.

## Re-applying after a diskimage-builder upgrade

The patch targets a file inside the installed package, so any `pip install
--upgrade diskimage-builder` silently reverts it. After upgrading, re-apply the
patch and re-run the verification above.
