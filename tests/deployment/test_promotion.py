import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/promote-deployment.sh'
OVERLAY = 'applications/tasks-app/overlays/homelab/kustomization.yaml'

class PromotionTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.exists(), 'promotion helper must exist')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = dict(os.environ, GIT_AUTHOR_NAME='Test', GIT_COMMITTER_NAME='Test',
                        GIT_AUTHOR_EMAIL='test@example.invalid', GIT_COMMITTER_EMAIL='test@example.invalid',
                        GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
        self.source = self.make_repo('source')
        self.deploy = self.make_repo('deploy')
        self.sha = self.git(self.source, 'rev-parse', 'HEAD').strip()
        self.before = self.git(self.root / 'deploy.git', 'rev-parse', 'main').strip()
        bin = self.root / 'bin'
        bin.mkdir()
        fake = bin / 'kustomize'
        fake.write_text('''#!/usr/bin/env python3
import os, pathlib, subprocess, sys
p=pathlib.Path('kustomization.yaml')
tag=sys.argv[-1].rsplit(':',1)[1]
p.write_text('tag: '+tag+'\\n')
if os.environ.get('BAD_EDIT'):
 pathlib.Path('../../../../unrelated.txt').write_text('unapproved change')
if os.environ.get('RACE_ORIGIN') and not pathlib.Path(os.environ['RACE_MARKER']).exists():
 pathlib.Path(os.environ['RACE_MARKER']).touch()
 other=os.environ['RACE_CLONE']
 subprocess.run(['git','clone',os.environ['RACE_ORIGIN'],other],check=True,capture_output=True)
 pathlib.Path(other,'concurrent.txt').write_text('preserve this edit')
 subprocess.run(['git','-C',other,'add','concurrent.txt'],check=True)
 subprocess.run(['git','-C',other,'commit','-m','Concurrent developer edit'],check=True,capture_output=True)
 subprocess.run(['git','-C',other,'push','origin','main'],check=True,capture_output=True)
''')
        fake.chmod(0o755)
        self.env['PATH'] = str(bin) + os.pathsep + os.environ['PATH']

    def git(self, directory, *args):
        return subprocess.check_output(['git', '-C', str(directory), *args], env=self.env, text=True, stderr=subprocess.DEVNULL)

    def make_repo(self, name):
        bare, working = self.root / (name + '.git'), self.root / name
        self.git(self.root, 'init', '--bare', '--initial-branch=main', str(bare))
        self.git(self.root, 'init', '--initial-branch=main', str(working))
        (working / OVERLAY).parent.mkdir(parents=True)
        (working / OVERLAY).write_text('tag: initial\n')
        (working / 'unrelated.txt').write_text('original')
        self.git(working, 'add', '.')
        self.git(working, 'commit', '-m', 'Initial')
        self.git(working, 'remote', 'add', 'origin', str(bare))
        self.git(working, 'push', '-u', 'origin', 'main')
        return working

    def promote(self, sha=None):
        return subprocess.run(['bash', str(SCRIPT), str(self.deploy), str(self.source), sha or self.sha],
                              env=self.env, text=True, capture_output=True, timeout=40)

    def remote(self, path):
        return self.git(self.root / 'deploy.git', 'show', 'main:' + path)

    def test_promotes_only_image_file_and_is_idempotent(self):
        result = self.promote()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.remote(OVERLAY), 'tag: ' + self.sha[:12] + '\n')
        self.assertEqual(self.remote('unrelated.txt'), 'original')
        first = self.git(self.root / 'deploy.git', 'rev-parse', 'main')
        self.assertEqual(self.promote().returncode, 0)
        self.assertEqual(self.git(self.root / 'deploy.git', 'rev-parse', 'main'), first)

    def test_rejects_invalid_or_stale_source_sha(self):
        self.assertNotEqual(self.promote('not-a-sha').returncode, 0)
        (self.source / 'new.txt').write_text('new revision')
        self.git(self.source, 'add', 'new.txt')
        self.git(self.source, 'commit', '-m', 'New source')
        self.git(self.source, 'push', 'origin', 'main')
        self.assertIn('checkout differs', self.promote().stderr)
        self.git(self.source, 'checkout', '--detach', self.sha)
        result = self.promote()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('superseded', result.stderr)
        self.assertEqual(self.git(self.root / 'deploy.git', 'rev-parse', 'main').strip(), self.before)

    def test_rejects_dirty_checkout_without_losing_edits(self):
        (self.deploy / 'unrelated.txt').write_text('local user edit')
        self.assertNotEqual(self.promote().returncode, 0)
        self.assertEqual((self.deploy / 'unrelated.txt').read_text(), 'local user edit')
        self.assertEqual(self.remote('unrelated.txt'), 'original')

    def test_rejects_unexpected_render_edits(self):
        self.env['BAD_EDIT'] = '1'
        self.assertNotEqual(self.promote().returncode, 0)
        self.assertEqual(self.git(self.root / 'deploy.git', 'rev-parse', 'main').strip(), self.before)

    def test_concurrent_remote_edit_is_preserved_on_retry(self):
        self.env.update(RACE_ORIGIN=str(self.root / 'deploy.git'), RACE_MARKER=str(self.root / 'raced'),
                        RACE_CLONE=str(self.root / 'other'))
        result = self.promote()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.remote('concurrent.txt'), 'preserve this edit')
        self.assertEqual(self.remote(OVERLAY), 'tag: ' + self.sha[:12] + '\n')

if __name__ == '__main__':
    unittest.main()
