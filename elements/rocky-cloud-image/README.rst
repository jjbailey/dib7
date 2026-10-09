=================
rocky-cloud-image
=================

Use a Rocky Linux cloud image as the baseline for built disk images.

diskimage-builder 3.42.0 ships no cloud-image element for Rocky Linux, only
``rocky-container``. This element fills that gap and is modelled on the
upstream ``centos`` element.

Environment Variables
---------------------

DIB_RELEASE
  :Required: No
  :Default: 10
  :Description: Rocky Linux major release. Selects the directory under
      ``https://dl.rockylinux.org/pub/rocky/``.

DIB_FLAVOR
  :Required: No
  :Default: GenericCloud-Base
  :Description: Image variant to download, for example ``GenericCloud-LVM``
      or ``EC2-Base``.

BASE_IMAGE_FILE
  :Required: No
  :Default: Rocky-$DIB_RELEASE-$DIB_FLAVOR.latest.$ARCH.qcow2
  :Description: Image file to download. The default tracks Rocky's stable
      ``.latest`` name, so point releases need no change here. Set this to a
      dated build such as
      ``Rocky-10-GenericCloud-Base-10.2-20260525.0.x86_64.qcow2`` when a
      reproducible image is required.

DIB_CLOUD_IMAGES
  :Required: No
  :Default: https://dl.rockylinux.org/pub/rocky/$DIB_RELEASE/images/$ARCH
  :Description: Base URL to fetch the image and its checksum from.

DIB_LOCAL_IMAGE
  :Required: No
  :Default: unset
  :Description: Path to a local qcow2 to use instead of downloading. No
      checksum is verified in this case.

Notes
-----

Supported architectures are x86_64 and aarch64.

The download is verified against Rocky's ``<image>.CHECKSUM`` file, which is
BSD style (``SHA256 (file) = hash``) rather than the ``<image>.SHA256SUM``
that the ``centos`` element expects. GNU ``sha256sum --check`` reads both.
