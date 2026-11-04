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

    def test_publish_validation_rejects_invalid_scope_and_optional_fields(self):
        with self.assertRaisesRegex(ValueError, "scope"):
            publish.validate(self.image(scope=["not-a-mapping"]))
        with self.assertRaisesRegex(ValueError, "project"):
            publish.validate(self.image(project=123))
        with self.assertRaisesRegex(ValueError, "extra"):
            publish.validate(self.image(extra="unknown"))

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
        credentials = reconcile_aws.AwsCredentials(profile=profile)
        with patch.object(reconcile_aws.subprocess, "run", return_value=result) as run:
            reconcile_aws.live_ami_ids("us-east-1", ["ami-1"], credentials)
        return run.call_args.args[0]

    def test_region_and_profile_keep_their_values(self):
        argv = self.describe_images_argv("lab")
        self.assertEqual(argv[argv.index("--region") + 1], "us-east-1")
        self.assertEqual(argv[argv.index("--profile") + 1], "lab")

    def test_no_profile_argument_without_profile(self):
        self.assertNotIn("--profile", self.describe_images_argv(None))

class ReconcileExitStatusTests(unittest.TestCase):
    def test_all_providers_return_success_after_removing_rows(self):
        for provider in ["aws", "azure", "gcp", "openstack", "vsphere"]:
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
                    elif provider == "azure":
                        # Only a retired row: no image lookup, so no client.
                        stack.enter_context(patch.object(module, "ComputeManagementClient", side_effect=AssertionError("unexpected cloud call")))
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

class AzureCredentialTests(unittest.TestCase):
    SUBSCRIPTION = "00000000-0000-0000-0000-000000000001"

    def setUp(self):
        self.module = load_script("reconcile-catalog-azure.py", "reconcile_azure_credential_test")
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.vault = self.root / "azure.yml"
        self.vault.write_text("$ANSIBLE_VAULT;1.1;AES256\n")
        self.password = self.root / "vault-pass"
        self.password.write_text("test\n")
        self.environ = patch.dict(self.module.os.environ, {
            "DIB7_VENV_BIN": str(self.root),
            "VAULT_PASSWORD_FILE": str(self.password),
        }, clear=True)
        self.environ.start()

    def tearDown(self):
        self.environ.stop()
        self.directory.cleanup()

    def fake_vault(self, projects):
        # Stand-in for ansible-vault view: print the decrypted YAML.
        plaintext = self.root / "plaintext.json"
        plaintext.write_text(json.dumps({"azure_projects": projects}))
        binary = self.root / "ansible-vault"
        binary.write_text(f"#!/bin/sh\ncat '{plaintext}'\n")
        binary.chmod(0o755)

    def entry(self, **updates):
        entry = {"tenant_id": "tenant", "client_id": "client", "client_secret": "secret",
                 "subscription_id": self.SUBSCRIPTION}
        entry.update(updates)
        return entry

    def credential(self):
        with patch.object(self.module, "ClientSecretCredential") as client_secret, \
                patch.object(self.module, "DefaultAzureCredential") as default:
            self.module.azure_credential(self.SUBSCRIPTION, self.vault)
        return client_secret, default

    def test_environment_service_principal_wins_without_reading_the_vault(self):
        self.module.os.environ.update(AZURE_TENANT="env-tenant", AZURE_CLIENT_ID="env-client", AZURE_SECRET="env-secret")
        with patch.object(self.module, "read_vault", side_effect=AssertionError("vault read")):
            client_secret, _ = self.credential()
        client_secret.assert_called_once_with("env-tenant", "env-client", "env-secret")

    def test_vault_service_principal_for_the_reconciled_subscription(self):
        self.fake_vault({"other": self.entry(subscription_id="other-sub", client_id="wrong"),
                         "lab": self.entry()})
        client_secret, default = self.credential()
        client_secret.assert_called_once_with("tenant", "client", "secret")
        default.assert_not_called()

    def test_falls_back_when_the_vault_has_no_entry_for_the_subscription(self):
        self.fake_vault({"other": self.entry(subscription_id="other-sub")})
        client_secret, default = self.credential()
        client_secret.assert_not_called()
        default.assert_called_once_with()

    def test_falls_back_without_a_password_file_instead_of_prompting(self):
        del self.module.os.environ["VAULT_PASSWORD_FILE"]
        self.fake_vault({"lab": self.entry()})
        with patch.object(sys.modules["reconcile_catalog_common"], "_vault_password_file", return_value=None):
            client_secret, default = self.credential()
        client_secret.assert_not_called()
        default.assert_called_once_with()

    def test_ambiguous_subscription_requires_a_target_project(self):
        self.fake_vault({"east": self.entry(), "west": self.entry(client_id="west-client")})
        with self.assertRaisesRegex(ValueError, "AZURE_TARGET_PROJECT"):
            self.credential()
        self.module.os.environ["AZURE_TARGET_PROJECT"] = "west"
        client_secret, _ = self.credential()
        client_secret.assert_called_once_with("tenant", "west-client", "secret")

    def test_target_project_for_another_subscription_is_refused(self):
        self.fake_vault({"other": self.entry(subscription_id="other-sub")})
        self.module.os.environ["AZURE_TARGET_PROJECT"] = "other"
        with self.assertRaisesRegex(ValueError, "not " + self.SUBSCRIPTION):
            self.credential()

    def test_failed_decryption_is_reported(self):
        binary = self.root / "ansible-vault"
        binary.write_text("#!/bin/sh\nexit 1\n")
        binary.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "could not decrypt"):
            self.credential()

class VaultCredentialOrderTests(unittest.TestCase):
    """Flag, then exported variables, then the vault, then cached logins."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.vault = self.root / "vault.yml"
        self.vault.write_text("$ANSIBLE_VAULT;1.1;AES256\n")
        self.password = self.root / "vault-pass"
        self.password.write_text("test\n")
        self.environ = patch.dict("os.environ", {
            "DIB7_VENV_BIN": str(self.root),
            "VAULT_PASSWORD_FILE": str(self.password),
        }, clear=True)
        self.environ.start()

    def tearDown(self):
        self.environ.stop()
        self.directory.cleanup()

    def fake_vault(self, document):
        plaintext = self.root / "plaintext.json"
        plaintext.write_text(json.dumps(document))
        binary = self.root / "ansible-vault"
        binary.write_text(f"#!/bin/sh\ncat '{plaintext}'\n")
        binary.chmod(0o755)

    def no_vault_read(self, module):
        return patch.object(module, "read_vault", side_effect=AssertionError("vault read"))

    # AWS
    AWS = {"aws_projects": {"111111111111": {"aws_account_id": "111111111111",
                                             "aws_access_key_id": "AK", "aws_secret_access_key": "SK",
                                             "aws_session_token": ""}}}

    def test_aws_profile_flag_and_exported_variables_skip_the_vault(self):
        with self.no_vault_read(reconcile_aws):
            self.assertEqual(reconcile_aws.aws_credentials("111111111111", self.vault, "mine").profile, "mine")
            for name in reconcile_aws.AWS_ENVIRONMENT:
                with patch.dict("os.environ", {name: "x"}):
                    credentials = reconcile_aws.aws_credentials("111111111111", self.vault)
                self.assertIsNone(credentials.profile)
                self.assertIsNone(credentials.env)

    def test_aws_vault_keys_reach_the_cli_environment(self):
        self.fake_vault(self.AWS)
        credentials = reconcile_aws.aws_credentials("111111111111", self.vault)
        self.assertEqual(credentials.env["AWS_ACCESS_KEY_ID"], "AK")
        self.assertEqual(credentials.env["AWS_SECRET_ACCESS_KEY"], "SK")
        self.assertNotIn("AWS_SESSION_TOKEN", credentials.env)
        result = Mock(stdout='{"Images": []}')
        with patch.object(reconcile_aws.subprocess, "run", return_value=result) as run:
            reconcile_aws.live_ami_ids("us-east-1", ["ami-1"], credentials)
        self.assertEqual(run.call_args.kwargs["env"]["AWS_ACCESS_KEY_ID"], "AK")

    def test_aws_cli_chain_without_a_vault_entry(self):
        self.fake_vault(self.AWS)
        credentials = reconcile_aws.aws_credentials("222222222222", self.vault)
        self.assertIsNone(credentials.env)
        self.assertIsNone(credentials.profile)

    # GCP
    def test_gcp_exported_key_file_skips_the_vault(self):
        reconcile_gcp = load_script("reconcile-catalog-gcp.py", "reconcile_gcp_credential_test")
        with patch.dict("os.environ", {"GOOGLE_APPLICATION_CREDENTIALS": "/k.json"}), \
                self.no_vault_read(reconcile_gcp), \
                patch.object(reconcile_gcp.google.auth, "default", return_value=("env", None)) as default:
            self.assertEqual(reconcile_gcp.gcp_credentials("lab", self.vault)[0], "env")
        default.assert_called_once()

    def test_gcp_vault_service_account_then_defaults(self):
        reconcile_gcp = load_script("reconcile-catalog-gcp.py", "reconcile_gcp_credential_test")
        key = {"type": "service_account", "project_id": "lab", "client_email": "x@y"}
        self.fake_vault({"gcp_projects": {"lab": {"gcp_project": "lab", "service_account_key": json.dumps(key)}}})
        with patch.object(reconcile_gcp.service_account.Credentials, "from_service_account_info",
                          return_value="vault") as info, \
                patch.object(reconcile_gcp.google.auth, "default", return_value=("ambient", None)) as default:
            self.assertEqual(reconcile_gcp.gcp_credentials("lab", self.vault), ("vault", "lab"))
            self.assertEqual(info.call_args.args[0]["client_email"], "x@y")
            default.assert_not_called()
            self.assertEqual(reconcile_gcp.gcp_credentials("other", self.vault)[0], "ambient")

    # OpenStack
    OPENSTACK = {"openstack_projects": {"9999": {
        "auth_url": "https://keystone/v3", "username": "u", "password": "p",
        "project_id": 9999, "project_name": "lab", "region_name": "R0"}}}

    def test_openstack_exported_variables_skip_the_vault(self):
        module = load_script("reconcile-catalog-openstack.py", "reconcile_openstack_credential_test")
        with patch.dict("os.environ", {"OS_AUTH_URL": "a", "OS_USERNAME": "u", "OS_PASSWORD": "p",
                                       "OS_PROJECT_NAME": "lab"}), \
                self.no_vault_read(module), \
                patch.object(module.openstack, "connect") as connect:
            module.openstack_connection(self.vault, "lab", "R1")
        connect.assert_called_once_with(region_name="R1")

    def test_openstack_vault_entry_alone(self):
        module = load_script("reconcile-catalog-openstack.py", "reconcile_openstack_credential_test")
        self.fake_vault(self.OPENSTACK)
        with patch.object(module.openstack, "connect") as connect:
            module.openstack_connection(self.vault, "lab", "R1")
        connect.assert_called_once_with(
            load_envvars=False, load_yaml_config=False, auth_url="https://keystone/v3",
            username="u", password="p", project_id="9999", project_name="lab", region_name="R1")

    def test_openstack_without_any_credentials_says_what_to_set(self):
        module = load_script("reconcile-catalog-openstack.py", "reconcile_openstack_credential_test")
        self.fake_vault(self.OPENSTACK)
        with self.assertRaisesRegex(ValueError, "vaults/openstack.yml"):
            module.openstack_connection(self.vault, "other", "R1")

    # vSphere
    VSPHERE = {"vcenter_hostname": "flat", "vcenter_username": "fu", "vcenter_password": "fp",
               "vsphere_projects": {"site-a": {"vcenter_hostname": "vc1", "vcenter_username": "u",
                                            "vcenter_password": "p"}}}

    def test_vsphere_exported_variables_skip_the_vault(self):
        module = load_script("reconcile-catalog-vsphere.py", "reconcile_vsphere_credential_test")
        exported = {"vcenter_hostname": "h", "vcenter_username": "u", "VCENTER_PASSWORD": "p"}
        with patch.dict("os.environ", exported), self.no_vault_read(module):
            self.assertEqual(module.vcenter_environment("site-a", self.vault)["vcenter_password"], "p")

    def test_vsphere_vault_entry_for_the_catalog_label(self):
        module = load_script("reconcile-catalog-vsphere.py", "reconcile_vsphere_credential_test")
        self.fake_vault(self.VSPHERE)
        self.assertEqual(module.vcenter_environment("site-a", self.vault)["vcenter_hostname"], "vc1")
        self.assertEqual(module.vcenter_environment("legacy", self.vault)["vcenter_hostname"], "flat")
        self.assertEqual(module.vcenter_environment(None, self.vault)["vcenter_hostname"], "flat")
        with self.assertRaisesRegex(ValueError, "missing vCenter environment"):
            module.vcenter_environment("elsewhere", self.vault)

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
