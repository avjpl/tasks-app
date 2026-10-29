"""Promotion against real disposable Git remotes and real Kustomize renders."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/promote-colocated.py'
OVERLAY = 'deploy/overlays/homelab/kustomization.yaml'


class Promotion(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.exists(), 'colocated promoter must exist')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'source'
        self.remote = self.root / 'origin.git'
        self.env = dict(os.environ, GIT_AUTHOR_NAME='Test', GIT_COMMITTER_NAME='Test',
                        GIT_AUTHOR_EMAIL='test@example.invalid',
                        GIT_COMMITTER_EMAIL='test@example.invalid',
                        GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
        self.git(self.root, 'init', '--bare', '--initial-branch=main', str(self.remote))
        self.git(self.root, 'init', '--initial-branch=main', str(self.repo))
        shutil.copytree(ROOT / 'deploy', self.repo / 'deploy')
        shutil.copytree(ROOT / 'argocd', self.repo / 'argocd')
        (self.repo / 'scripts').mkdir()
        shutil.copy2(ROOT / 'scripts/validate-deployment.py', self.repo / 'scripts')
        (self.repo / 'apps').mkdir()
        (self.repo / 'apps/source.txt').write_text('source v1\n')
        self.commit('Initial source')
        self.baseline = self.git(self.repo, 'rev-parse', 'HEAD').strip()
        self.set_tags(self.baseline[:12])
        self.commit('Pin initial image pair')
        self.sha = self.git(self.repo, 'rev-parse', 'HEAD').strip()
        self.git(self.repo, 'remote', 'add', 'origin', str(self.remote))
        self.git(self.repo, 'push', '-u', 'origin', 'main')

    def git(self, cwd, *args):
        return subprocess.check_output(['git', '-C', str(cwd), *args], env=self.env,
                                       text=True, stderr=subprocess.DEVNULL)

    def commit(self, message):
        self.git(self.repo, 'add', '.')
        self.git(self.repo, 'commit', '-m', message)

    def set_tags(self, tag, web_tag=None):
        path = self.repo / OVERLAY
        doc = yaml.safe_load(path.read_text())
        for image in doc['images']:
            image['newTag'] = web_tag if image['name'] == 'tasks-web' and web_tag else tag
        path.write_text(yaml.safe_dump(doc, sort_keys=False))

    def promote(self, sha=None, check=False):
        command = [sys.executable, '-B', str(SCRIPT), str(self.repo), sha or self.sha]
        if check:
            command.append('--check-build')
        return subprocess.run(command, env=self.env, capture_output=True, text=True, timeout=45)

    def remote_head(self):
        return self.git(self.remote, 'rev-parse', 'main').strip()

    def publish(self):
        self.sha = self.git(self.repo, 'rev-parse', 'HEAD').strip()
        self.git(self.repo, 'push', 'origin', 'main')

    def test_promotes_exact_pair_preserves_caller_and_is_idempotent(self):
        before = (self.repo / OVERLAY).read_text()
        result = self.promote()
        self.assertEqual(result.returncode, 0, result.stderr)
        changed = self.git(self.remote, 'diff', '--name-only', self.sha, 'main').splitlines()
        self.assertEqual(changed, [OVERLAY])
        old_doc = yaml.safe_load(before)
        for image in old_doc['images']:
            image['newTag'] = self.sha[:12]
        self.assertEqual(yaml.safe_load(self.git(self.remote, 'show', 'main:' + OVERLAY)), old_doc)
        self.assertEqual((self.repo / OVERLAY).read_text(), before)
        self.assertEqual(self.git(self.repo, 'status', '--porcelain'), '')
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD').strip(), self.sha)
        first = self.remote_head()
        result = self.promote()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.remote_head(), first)
        self.assertEqual(len(self.git(self.repo, 'worktree', 'list', '--porcelain').split('worktree ')), 2)

    def test_rejects_invalid_sha_and_mismatched_checkout(self):
        for sha in ['invalid', 'a' * 40]:
            with self.subTest(sha=sha):
                self.assertNotEqual(self.promote(sha).returncode, 0)
        self.assertEqual(self.remote_head(), self.sha)

    def test_rejects_dirty_checkout_without_losing_user_edits(self):
        (self.repo / 'unrelated.txt').write_text('keep this')
        self.assertNotEqual(self.promote().returncode, 0)
        self.assertEqual((self.repo / 'unrelated.txt').read_text(), 'keep this')
        self.assertEqual(self.remote_head(), self.sha)

    def test_rejects_superseded_source(self):
        (self.repo / 'apps/source.txt').write_text('source v2')
        self.commit('Newer source')
        self.git(self.repo, 'push', 'origin', 'main')
        newer = self.remote_head()
        self.git(self.repo, 'checkout', '--detach', self.sha)
        result = self.promote()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('superseded', result.stderr)
        self.assertEqual(self.remote_head(), newer)

    def test_rejects_invalid_render_before_push(self):
        with (self.repo / 'deploy/base/kustomization.yaml').open('a') as stream:
            stream.write('  - missing.yaml\n')
        self.commit('Broken render')
        self.publish()
        self.assertNotEqual(self.promote().returncode, 0)
        self.assertEqual(self.remote_head(), self.sha)
        self.assertEqual(self.git(self.repo, 'status', '--porcelain'), '')

    def test_concurrent_push_is_preserved_without_stale_retry(self):
        (self.repo / 'concurrent.txt').write_text('keep newer change')
        self.commit('Concurrent source')
        newer = self.git(self.repo, 'rev-parse', 'HEAD').strip()
        self.git(self.repo, 'push', 'origin', 'HEAD:refs/heads/race')
        self.git(self.repo, 'checkout', '--detach', self.sha)
        hook = self.remote / 'hooks/pre-receive'
        hook.write_text('#!/bin/sh\nunset GIT_QUARANTINE_PATH\n'
                        f'git update-ref refs/heads/main {newer} {self.sha}\n')
        hook.chmod(0o755)
        result = self.promote()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.remote_head(), newer)
        self.assertEqual(self.git(self.remote, 'show', 'main:concurrent.txt'), 'keep newer change')
        self.assertEqual(self.git(self.repo, 'status', '--porcelain'), '')

    def test_manifest_only_change_skips_build(self):
        (self.repo / 'README.md').write_text('deployment docs')
        self.commit('Docs after promotion')
        self.publish()
        result = self.promote(check=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'build=false')

    def test_unpromoted_source_followed_by_manifest_change_still_builds(self):
        (self.repo / 'apps/source.txt').write_text('source v2')
        self.commit('Source change')
        (self.repo / 'README.md').write_text('later docs')
        self.commit('Later deployment docs')
        self.publish()
        self.assertEqual(self.promote(check=True).stdout.strip(), 'build=true')

    def test_unknown_baseline_builds_and_mismatched_pair_is_rejected(self):
        self.set_tags('0123456789ab')
        self.commit('Unknown old images')
        self.publish()
        self.assertEqual(self.promote(check=True).stdout.strip(), 'build=true')
        self.set_tags('0123456789ab', 'abcdef012345')
        self.commit('Mismatched pair')
        self.publish()
        self.assertNotEqual(self.promote(check=True).returncode, 0)
        self.assertNotEqual(self.promote().returncode, 0)

    def test_ambiguous_baseline_resolution_requires_build(self):
        spec = importlib.util.spec_from_file_location('promoter', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # An actual 12-digit SHA collision is impractical to manufacture. Simulate
        # only Git's ambiguity result; still execute the real decision function.
        with patch.object(module, 'resolve_commit', return_value=None):
            self.assertTrue(module.requires_build(self.repo, self.sha))


if __name__ == '__main__':
    unittest.main()
