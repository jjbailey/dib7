# Fedora Server 43+

---

## Patch required to build Fedora Server 43+

Fedora changed the naming convention for the ISO downloads. Apply the following
patch to diskimage-builder 3.41.0:

<!-- markdownlint-disable MD013 -->
```text
--- 10-fedora-cloud-image~  2026-01-05 16:25:31.455235058 -0800
+++ 10-fedora-cloud-image  2026-03-27 08:51:56.592704975 -0700
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
<!-- markdownlint-enable MD013 -->
