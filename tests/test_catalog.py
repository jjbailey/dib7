#!/usr/bin/env python3
# tests/test_catalog.py
# vim: set tabstop=4 shiftwidth=4 expandtab:


"""Focused tests for image publication and reconciliation safety."""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "bin"
sys.path.insert(0, str(BIN))


def load_script(filename, module_name):
    spec = importlib.util.spec_from_file_location(module_name, BIN / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


publish = load_script("publish-image-catalog.py", "publish_image_catalog")
reconcile_common = load_script("reconcile_catalog_common.py", "reconcile_catalog_common_test")
reconcile_aws = load_script("reconcile-catalog-aws.py", "reconcile_catalog_aws")


class CatalogEntryTests(unittest.TestCase):
    def image(self, **updates):
        entry = {
            "logical_name": "ubuntu-base",
            "provider": "openstack",
            "artifact_id": "image-1",
            "artifact_type": "glance_image",
            "version": "2026-09-14T120000Z",
            "architecture": "amd64",
            "boot_mode": "uefi",
            "source_build": "ubuntu-base",
            "status": "published",
        }
        entry.update(updates)
        return entry

    def test_publish_validation_rejects_unknown_provider_and_status(self):
        with self.assertRaisesRegex(ValueError, "unsupported provider"):
            publish.validate(self.image(provider="oracle"))
        with self.assertRaisesRegex(ValueError, "unsupported status"):
            publish.validate(self.image(status="active"))

    def test_publish_supersede_replaces_matching_artifact_only(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "image-catalog.json"
            old = Path(directory) / "old.json"
            replacement = Path(directory) / "replacement.json"
            unrelated = Path(directory) / "unrelated.json"
            old.write_text(json.dumps(self.image(artifact_id="old", version="old")))
            replacement.write_text(json.dumps(self.image(artifact_id="new", version="new")))
            unrelated.write_text(json.dumps(self.image(
                provider="aws", artifact_type="ami", artifact_id="ami-1")))

            with patch.object(sys, "argv", ["publish", "--catalog", str(catalog), "--entry", str(old)]):
                publish.main()
            with patch.object(sys, "argv", ["publish", "--catalog", str(catalog), "--entry", str(unrelated)]):
                publish.main()
            with patch.object(sys, "argv", ["publish", "--catalog", str(catalog), "--entry", str(replacement), "--supersede"]):
                publish.main()

            images = json.loads(catalog.read_text())["images"]
            self.assertEqual(len(images), 2)
            self.assertIn("new", {image["artifact_id"] for image in images})
            self.assertNotIn("old", {image["artifact_id"] for image in images})
            self.assertIn("ami-1", {image["artifact_id"] for image in images})


class ReconcileSafetyTests(unittest.TestCase):
    def image(self, artifact_id, status="published", provider="openstack", scope="project-a"):
        return {
            "logical_name": artifact_id,
            "provider": provider,
            "artifact_id": artifact_id,
            "artifact_type": "glance_image",
            "version": "v1",
            "status": status,
            "scope": scope,
        }

    def write_catalog(self, directory, images):
        path = Path(directory) / "image-catalog.json"
        path.write_text(json.dumps({"schema_version": 1, "images": images}))
        return path

    def test_dry_run_does_not_write_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            stale = self.image("gone")
            path = self.write_catalog(directory, [stale])
            before = path.read_text()
            result = reconcile_common.reconcile(
                path, "openstack", [(stale, "missing")], [],
                lambda image: image["scope"] == "project-a", "project-a", True, False)
            self.assertEqual(result, 0)
            self.assertEqual(path.read_text(), before)

    def test_majority_guard_requires_force_and_force_removes_scoped_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            stale_a = self.image("gone-a")
            stale_b = self.image("gone-b")
            active = self.image("kept")
            outside = self.image("outside", scope="project-b")
            path = self.write_catalog(directory, [stale_a, stale_b, active, outside])
            stale = [(stale_a, "missing"), (stale_b, "missing")]
            scope = lambda image: image["scope"] == "project-a"

            with self.assertRaisesRegex(ValueError, "refusing to remove"):
                reconcile_common.reconcile(path, "openstack", stale, [], scope, "project-a", False, False)

            result = reconcile_common.reconcile(path, "openstack", stale, [], scope, "project-a", False, True)
            self.assertEqual(result, 2)
            remaining = json.loads(path.read_text())["images"]
            self.assertEqual({image["artifact_id"] for image in remaining}, {"kept", "outside"})

    def test_retired_entries_are_removed_without_majority_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            retired = self.image("retired", status="retired")
            active = self.image("active")
            path = self.write_catalog(directory, [retired, active])
            result = reconcile_common.reconcile(
                path, "openstack", [], [retired], lambda image: True,
                "project-a", False, False)
            self.assertEqual(result, 1)
            self.assertEqual([image["artifact_id"] for image in json.loads(path.read_text())["images"]], ["active"])


class AwsCommandTests(unittest.TestCase):
    def describe_images_argv(self, profile):
        result = Mock(stdout='{"Images": []}')
        with patch.object(reconcile_aws.subprocess, "run", return_value=result) as run:
            reconcile_aws.live_ami_ids("us-east-1", ["ami-1"], profile)
        return run.call_args.args[0]

    def test_region_and_profile_keep_their_values(self):
        argv = self.describe_images_argv("lab")
        self.assertEqual(argv[argv.index("--region") + 1], "us-east-1")
        self.assertEqual(argv[argv.index("--profile") + 1], "lab")

    def test_no_profile_argument_without_profile(self):
        self.assertNotIn("--profile", self.describe_images_argv(None))


if __name__ == "__main__":
    unittest.main()
