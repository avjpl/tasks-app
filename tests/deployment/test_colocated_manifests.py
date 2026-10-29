"""Exercise the Application and resource ownership boundary."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ManifestBoundary(unittest.TestCase):
    def setUp(self):
        path = ROOT / 'scripts/validate-deployment.py'
        self.assertTrue(path.exists(), 'colocated validator must exist')
        spec = importlib.util.spec_from_file_location('validate_deployment', path)
        self.validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.validator)
        self.app = {
            'apiVersion': 'argoproj.io/v1alpha1', 'kind': 'Application',
            'metadata': {'name': 'tasks-app', 'namespace': 'argocd-app-tasks-app'},
            'spec': {
                'project': 'tasks-app',
                'source': {'repoURL': 'git@github.com:avjpl/tasks-app.git',
                           'targetRevision': 'main', 'path': 'deploy/overlays/homelab'},
                'destination': {'server': 'https://kubernetes.default.svc',
                                'namespace': 'tasks-app'},
            },
        }

    def test_accepts_colocated_application(self):
        self.validator.validate_application(self.app)

    def test_rejects_old_and_cross_paired_sources(self):
        new = self.app['spec']['source']
        old_repo = 'git@github.com:avjpl/application-deployments.git'
        old_path = 'applications/tasks-app/overlays/homelab'
        for repo, path in [(old_repo, old_path), (old_repo, new['path']),
                           (new['repoURL'], old_path), ('https://evil.invalid', new['path'])]:
            app = copy.deepcopy(self.app)
            app['spec']['source'].update(repoURL=repo, path=path)
            with self.subTest(repo=repo, path=path), self.assertRaises(ValueError):
                self.validator.validate_application(app)

    def test_rejects_widened_identity_and_scope(self):
        for path, value in [('metadata.name', 'other'), ('metadata.namespace', 'argocd'),
                            ('spec.project', 'platform'), ('spec.source.targetRevision', 'other'),
                            ('spec.destination.namespace', 'monitoring'),
                            ('spec.destination.server', 'https://other.invalid')]:
            app = copy.deepcopy(self.app)
            target = app
            parts = path.split('.')
            for key in parts[:-1]:
                target = target[key]
            target[parts[-1]] = value
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.validator.validate_application(app)

    def test_rejects_alternate_renderers_and_multi_source(self):
        for key in ['chart', 'plugin', 'helm', 'directory', 'ref', 'kustomize']:
            app = copy.deepcopy(self.app)
            app['spec']['source'][key] = {}
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validator.validate_application(app)
        app = copy.deepcopy(self.app)
        app['spec']['sources'] = [app['spec']['source']]
        with self.assertRaises(ValueError):
            self.validator.validate_application(app)

    def test_rejects_empty_foreign_and_cluster_resources(self):
        for objects in [[], [{'kind': 'Namespace', 'metadata': {'name': 'kube-system'}}],
                        [{'kind': 'Deployment', 'metadata': {'namespace': 'other'}}],
                        [{'kind': 'ClusterRole', 'metadata': {'namespace': 'tasks-app'}}],
                        [{'kind': 'AppProject', 'metadata': {'namespace': 'tasks-app'}}]]:
            with self.subTest(objects=objects), self.assertRaises(ValueError):
                self.validator.validate_workloads(objects)
        self.validator.validate_workloads([
            {'kind': 'Namespace', 'metadata': {'name': 'tasks-app'}},
            {'kind': 'Deployment', 'metadata': {'namespace': 'tasks-app'}},
        ])


if __name__ == '__main__':
    unittest.main()
