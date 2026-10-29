"""Offline validation of colocated tasks-app deployment ownership."""
from pathlib import Path
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = {'repoURL': 'git@github.com:avjpl/tasks-app.git',
          'targetRevision': 'main', 'path': 'deploy/overlays/homelab'}


def validate_application(document: dict) -> None:
    try:
        spec, meta = document['spec'], document['metadata']
        valid = (document['apiVersion'] == 'argoproj.io/v1alpha1'
                 and document['kind'] == 'Application'
                 and meta['name'] == 'tasks-app' and meta['namespace'] == 'argocd-app-tasks-app'
                 and spec['project'] == 'tasks-app' and spec['source'] == SOURCE
                 and 'sources' not in spec
                 and spec['destination'] == {'server': 'https://kubernetes.default.svc',
                                             'namespace': 'tasks-app'})
        if not valid:
            raise ValueError('Application must match the platform-approved boundary')
    except (KeyError, TypeError) as exc:
        raise ValueError('Incomplete Application') from exc


def validate_workloads(objects: list[dict]) -> None:
    allowed = {'ConfigMap', 'Service', 'Deployment', 'StatefulSet', 'Certificate',
               'ExternalSecret', 'SecretStore', 'NetworkPolicy', 'VirtualService'}
    if not objects:
        raise ValueError('Empty workload render is not a deployment')
    for obj in objects:
        meta = obj.get('metadata', {})
        if obj.get('kind') == 'Namespace':
            if meta.get('name') != 'tasks-app':
                raise ValueError('Only the existing tasks-app namespace is allowed')
        elif obj.get('kind') not in allowed or meta.get('namespace') != 'tasks-app':
            raise ValueError('Resource outside the platform-approved workload boundary')


def render(path: str) -> list[dict]:
    text = subprocess.check_output(['kubectl', 'kustomize', str(ROOT / path)], text=True)
    return [doc for doc in yaml.safe_load_all(text) if doc]


def main():
    applications = render('argocd/tasks-app')
    if len(applications) != 1:
        raise ValueError('Registration must contain exactly one Application')
    validate_application(applications[0])
    objects = render(SOURCE['path'])
    validate_workloads(objects)
    print(f'PASS: one approved Application and {len(objects)} scoped workload resources')


if __name__ == '__main__':
    main()
