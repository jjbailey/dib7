#!/usr/bin/env python3
# tests/test_catalog.py
# vim: set tabstop=4 shiftwidth=4 expandtab:

"""Focused tests for image publication and reconciliation safety."""

from contextlib import ExitStack
import importlib.util
import json
import subprocess
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

    def test_publish_supersede_keeps_projects_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "image-catalog.json"
            first = Path(directory) / "first.json"
            second = Path(directory) / "second.json"
            first.write_text(json.dumps(self.image(artifact_id="project-a", project="project-a")))
            second.write_text(json.dumps(self.image(artifact_id="project-b", project="project-b")))

            with patch.object(sys, "argv", ["publish", "--catalog", str(catalog), "--entry", str(first), "--supersede"]):
                publish.main()
            with patch.object(sys, "argv", ["publish", "--catalog", str(catalog), "--entry", str(second), "--supersede"]):
                publish.main()

            images = json.loads(catalog.read_text())["images"]
            self.assertEqual({image["artifact_id"] for image in images}, {"project-a", "project-b"})

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

class ExactRowRemovalTests(unittest.TestCase):
    def test_shared_artifact_key_removes_only_the_discovered_row(self):
        stale = {
            "logical_name": "centos10s-base", "provider": "vsphere",
            "artifact_id": "centos10s-base.ova", "artifact_type": "content_library_ova",
            "version": "1790476201", "status": "published",
            "scope": {"content_library": "Content_Library", "vcenter": "legacy"},
        }
        twin = dict(stale)
        twin["scope"] = {"content_library": "Content_Library"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image-catalog.json"
            path.write_text(json.dumps({"schema_version": 1, "images": [stale, twin]}))
            result = reconcile_common.reconcile(
                path, "vsphere", [(stale, "artifact not found")], [],
                lambda image: True, "legacy", False, True)
            remaining = json.loads(path.read_text())["images"]
            self.assertEqual(result, 1)
            self.assertEqual(len(remaining), 1)
            self.assertNotIn("vcenter", remaining[0]["scope"])

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

class ReconcileExitStatusTests(unittest.TestCase):
    def test_all_providers_return_success_after_removing_rows(self):
        for provider in ["aws", "gcp", "openstack", "vsphere"]:
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as directory:
                module = load_script(f"reconcile-catalog-{provider}.py", f"reconcile_{provider}_exit_test")
                catalog = Path(directory) / "catalog.json"
                catalog.write_text(json.dumps({"schema_version": 1, "images": [{
                    "provider": provider, "logical_name": "retired-image",
                    "artifact_id": "retired-id", "artifact_type": "content_library_ova",
                    "version": "v1", "status": "retired", "project": "test-project",
                    "region": "test-region",
                    "scope": {"content_library": "test-library", "vcenter": "test-vcenter"},
                }]}))
                argv = ["reconcile", "--catalog", str(catalog)]
                with ExitStack() as stack:
                    if provider == "aws":
                        stack.enter_context(patch.object(module, "live_ami_ids", side_effect=AssertionError("unexpected cloud call")))
                    elif provider == "gcp":
                        stack.enter_context(patch.object(module.google.auth, "default", return_value=(Mock(), "test-project")))
                        stack.enter_context(patch.object(module, "AuthorizedSession"))
                    elif provider == "openstack":
                        argv += ["--cloud", "test-cloud"]
                        connection = Mock(current_project_id="test-project")
                        connection.current_project.name = "test-project"
                        stack.enter_context(patch.object(module.openstack, "connect", return_value=connection))
                    else:
                        stack.enter_context(patch.object(module, "query_live_artifacts", return_value=(set(), set())))
                    stack.enter_context(patch.object(sys, "argv", argv))
                    self.assertEqual(module.main(), 0)
                self.assertEqual(json.loads(catalog.read_text())["images"], [])

    def test_aws_cli_success_and_error_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "catalog.json"
            catalog.write_text(json.dumps({"schema_version": 1, "images": [{
                "provider": "aws", "logical_name": "retired-image", "artifact_id": "ami-test",
                "version": "v1", "status": "retired", "region": "test-region",
            }]}))
            command = [sys.executable, str(BIN / "reconcile-catalog-aws.py"), "--catalog", str(catalog)]
            result = subprocess.run(command, text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(catalog.read_text())["images"], [])
            catalog.write_text("invalid JSON")
            result = subprocess.run(command, text=True, capture_output=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)

class CatalogSchemaTests(unittest.TestCase):
    """The catalog's shape is declared twice; keep the two declarations equal."""

    def test_publish_constants_track_the_catalog_schema(self):
        schema = json.loads((ROOT / "catalogs/image-catalog.schema.json").read_text())
        item = schema["properties"]["images"]["items"]
        self.assertFalse(item["additionalProperties"])
        self.assertEqual(publish.REQUIRED, set(item["required"]))
        self.assertEqual(publish.PROVIDERS, set(item["properties"]["provider"]["enum"]))
        self.assertEqual(publish.STATUSES, set(item["properties"]["status"]["enum"]))

if __name__ == "__main__":
    unittest.main()
