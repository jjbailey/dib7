#!/usr/bin/env python3
# tests/test_pipeline.py
# vim: set tabstop=4 shiftwidth=4 expandtab:

"""Runtime regressions using real tasks/helpers and local provider stand-ins."""

import copy
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
VENV_BIN = Path(os.environ.get('DIB7_VENV_BIN', Path.home() / '.dib7/bin'))

def tasks_file(name):
    return yaml.safe_load((ROOT / 'playbooks' / name).read_text())

@unittest.skipUnless((VENV_BIN / 'ansible-playbook').is_file(), 'requires project Ansible venv')
class AnsibleRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def run_tasks(self, tasks, variables, hosts='localhost', serial=None):
        play = {
            'hosts': 'all', 'gather_facts': False, 'strategy': 'linear',
            'vars': {'ansible_python_interpreter': sys.executable, **variables},
            'tasks': tasks,
        }
        if serial:
            play['serial'] = serial
        path = self.directory / 'test.yml'
        path.write_text(yaml.safe_dump([play], sort_keys=False))
        return subprocess.run(
            [str(VENV_BIN / 'ansible-playbook'), '-i', hosts + ',', '-c', 'local', str(path)],
            cwd=ROOT, text=True, capture_output=True, timeout=180,
        )

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_legacy_aws_profile_and_account_survive_selection(self):
        # Supply synthetic vault data directly; never open a real vault.
        tasks = [task for task in tasks_file('tasks/select-aws-project.yml')
                 if 'ansible.builtin.include_vars' not in task]
        tasks.append({'ansible.builtin.assert': {'that': [
            "aws_profile == 'selected-profile'",
            "aws_account_id == '123456789012'",
            "aws_task_env.AWS_PROFILE == 'selected-profile'",
        ]}})
        for keys in [('aws_profile', 'aws_account_id'), ('profile', 'account_id')]:
            with self.subTest(keys=keys):
                variables = {
                    'aws_region': 'us-west-2', 's3_bucket': 'test-bucket',
                    'vmimport_role_name': 'vmimport',
                    keys[0]: 'selected-profile', keys[1]: '123456789012',
                }
                self.assert_success(self.run_tasks(tasks, variables))

    def test_failed_aws_import_finalizer_allows_next_serial_host(self):
        tasks = tasks_file('import-ova-aws.yml')[0]['tasks']
        finalizer = next(task['always'] for task in tasks if 'always' in task)
        result = self.run_tasks([
            {'block': [{'ansible.builtin.fail': {'msg': 'simulated API failure'},
                        'register': 'import_task'}],
             'rescue': [{'ansible.builtin.debug': {'msg': 'failure recorded'}}],
             'always': finalizer},
            {'ansible.builtin.copy': {
                'dest': str(self.directory / '{{ inventory_hostname }}.reached'),
                'content': 'reached next task', 'mode': '0600',
            }},
        ], {}, hosts='first,second', serial=1)
        self.assert_success(result)
        for host in ['first', 'second']:
            self.assertTrue((self.directory / (host + '.reached')).exists())

    def test_conversion_retry_replaces_partial_output_and_preserves_build_run(self):
        # Exercise the entire conversion block, including stamp verification,
        # template rendering, rescue, and cleanup. Fake external tools let us
        # deterministically fail after writing output without real disk images.
        tool_dir = self.directory / 'bin'
        tool_dir.mkdir()
        qemu = tool_dir / 'qemu-img'
        qemu.write_text(f'#!{sys.executable}\n' + '''import json, pathlib, sys
if sys.argv[1] == 'convert':
    pathlib.Path(sys.argv[-1]).write_text('incomplete')
    if pathlib.Path('fail-conversion').exists():
        sys.exit(1)
    pathlib.Path(sys.argv[-1]).write_text(pathlib.Path(sys.argv[-2]).read_text())
else:
    print(json.dumps({'virtual-size': 33554432}))
''')
        qemu.chmod(0o755)
        ovf = tool_dir / 'ovftool'
        ovf.write_text(f'#!{sys.executable}\nimport pathlib, sys\npathlib.Path(sys.argv[-1]).write_text("ova")\n')
        ovf.chmod(0o755)
        variables = yaml.safe_load((ROOT / 'group_vars/all/main.yml').read_text())
        variables.update(yaml.safe_load((ROOT / 'group_vars/ubuntu/main.yml').read_text()))
        variables.update({'build_dir': str(self.directory), 'image_name': 'test-base'})
        (self.directory / 'test-base.built').write_text('1790000000\n')
        (self.directory / 'test-base.qcow2').write_text('complete disk contents')
        vmdk = self.directory / 'test-base.vmdk'
        vmdk.write_text('legacy partial disk')
        os.utime(vmdk, (2000000000, 2000000000))
        block = copy.deepcopy(tasks_file('convert-qcow2-to-ova.yml')[0]['tasks'][1])
        block['environment'] = {'PATH': str(tool_dir) + os.pathsep + os.environ['PATH']}
        for task in block['block']:
            if 'ansible.builtin.include_tasks' in task:
                task['ansible.builtin.include_tasks'] = str(ROOT / 'playbooks' / task['ansible.builtin.include_tasks'])
            if 'ansible.builtin.template' in task:
                task['ansible.builtin.template']['src'] = str(ROOT / 'templates/ovf-file.j2')
            # No backoff is needed for deterministic tool failures in tests.
            if 'retries' in task:
                task['retries'] = 0
                task['delay'] = 0
        failure = self.directory / 'fail-conversion'
        failure.touch()
        self.assert_success(self.run_tasks([block], variables))  # rescued failure
        self.assertEqual(vmdk.read_text(), 'legacy partial disk')
        self.assertFalse((self.directory / 'test-base.converted').exists())
        self.assertFalse((self.directory / '.test-base.vmdk.partial').exists())
        failure.unlink()
        self.assert_success(self.run_tasks([block], variables))
        self.assertEqual(vmdk.read_text(), 'complete disk contents')
        self.assertEqual((self.directory / 'test-base.converted').read_text(), '1790000000\n')
        self.assertFalse((self.directory / '.test-base.vmdk.partial').exists())

@unittest.skipUnless(shutil.which('pwsh'), 'requires PowerShell')
class VsphereRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.ova = Path(self.temporary.name) / 'test.ova'
        self.ova.write_text('test image')
        self.marker = Path(str(self.ova) + '.imported')
        self.uploads = Path(str(self.ova) + '.uploads')

    def run_helper(self, script, server='vc-a.example', fail_at='', existing=False):
        command = ['pwsh', '-NoProfile', '-NonInteractive', '-File',
                   str(ROOT / 'tests/vsphere-mocks.ps1'), '-Script', str(ROOT / 'bin' / script),
                   '-Ova', str(self.ova), '-Server', server, '-FailAt', fail_at]
        if existing:
            command.append('-Existing')
        return subprocess.run(command, text=True, capture_output=True, timeout=60)

    def test_upload_errors_fail_without_writing_marker(self):
        for script in ['import-ova-vsphere.ps1', 'import-ova-vsphere-template.ps1']:
            with self.subTest(script=script):
                result = self.run_helper(script, fail_at='upload')
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertFalse(self.marker.exists())
                self.assertNotIn('Successfully imported OVA', result.stdout)
                self.assertNotIn('Successfully created vSphere template', result.stdout)

    def test_template_conversion_and_placement_errors_fail(self):
        for stage in ['template', 'move']:
            with self.subTest(stage=stage):
                result = self.run_helper('import-ova-vsphere-template.ps1', fail_at=stage)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotIn('Successfully created vSphere template', result.stdout)

    def test_markers_require_matching_vcenter_and_accept_same_target(self):
        digest = hashlib.sha1(self.ova.read_bytes()).hexdigest()
        for script in ['import-ova-vsphere.ps1', 'import-ova-vsphere-template.ps1']:
            for previous in [f'{digest}  SharedLibrary', f'{digest}  vc-a.example  SharedLibrary']:
                with self.subTest(script=script, previous=previous):
                    self.marker.write_text(previous)
                    self.uploads.unlink(missing_ok=True)
                    result = self.run_helper(script, server='vc-b.example', existing=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(self.uploads.read_text().splitlines(), ['vc-b.example'])
                    # With no remote description, the scoped marker still avoids
                    # another upload on the same vCenter and library.
                    result = self.run_helper(script, server='vc-b.example', existing=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(self.uploads.read_text().splitlines(), ['vc-b.example'])

if __name__ == '__main__':
    unittest.main()
