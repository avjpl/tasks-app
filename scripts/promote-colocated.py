"""Promote a trusted tested revision without rewriting the caller's checkout."""
import argparse
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import yaml

OVERLAY = 'deploy/overlays/homelab/kustomization.yaml'
IMAGES = {'tasks-api': 'ghcr.io/avjpl/tasks-api', 'tasks-web': 'ghcr.io/avjpl/tasks-web'}
BUILD_INPUTS = ['apps', 'package.json', 'bun.lock', 'bun.lockb', 'package-lock.json',
                'tsconfig.base.json', 'biome.json', '.dockerignore',
                '.github/workflows/ci.yml', '.github/workflows/release.yml']


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


def image_pair(text: str) -> tuple[dict, str]:
    document = yaml.safe_load(text)
    images = document.get('images', [])
    if len(images) != 2 or {image.get('name') for image in images} != set(IMAGES):
        raise ValueError('Expected exactly the API and web image pair')
    for image in images:
        if (image.get('newName') != IMAGES[image['name']]
                or set(image) != {'name', 'newName', 'newTag'}
                or not re.fullmatch(r'[0-9a-f]{12}', str(image.get('newTag', '')))):
            raise ValueError('Image selection must use the reviewed repository and SHA tag')
    tags = {str(image['newTag']) for image in images}
    if len(tags) != 1:
        raise ValueError('API and web image tags must match')
    return document, tags.pop()


def resolve_commit(repo: Path, prefix: str) -> str | None:
    objects = git(repo, 'rev-parse', '--disambiguate=' + prefix).splitlines()
    if len(objects) != 1 or git(repo, 'cat-file', '-t', objects[0]) != 'commit':
        return None
    return objects[0]


def requires_build(repo: Path, tested_sha: str) -> bool:
    _, tag = image_pair(git(repo, 'show', f'{tested_sha}:{OVERLAY}'))
    previous = resolve_commit(repo, tag)
    return previous is None or bool(git(repo, 'diff', '--name-only', previous, tested_sha,
                                        '--', *BUILD_INPUTS))


def update_tags(text: str, tag: str) -> str:
    # Replace only the two scalar spans; retain comments, formatting and all
    # unrelated manifest settings rather than serializing the entire YAML tree.
    expected, _ = image_pair(text)
    tree = yaml.compose(text)
    images = next(value for key, value in tree.value if key.value == 'images')
    spans = []
    for image in images.value:
        value = next(value for key, value in image.value if key.value == 'newTag')
        spans.append((value.start_mark.index, value.end_mark.index))
    for start, end in sorted(spans, reverse=True):
        text = text[:start] + f'"{tag}"' + text[end:]
    for image in expected['images']:
        image['newTag'] = tag
    if yaml.safe_load(text) != expected:
        raise ValueError('Promotion changed fields outside image tags')
    return text


def promote(repo: Path, tested_sha: str) -> None:
    git(repo, 'fetch', 'origin', 'main')
    remote = git(repo, 'rev-parse', 'FETCH_HEAD')
    _, current_tag = image_pair(git(repo, 'show', f'{remote}:{OVERLAY}'))
    tag = tested_sha[:12]
    if current_tag == tag:
        print(f'Already promoted {tag}')
        return
    if remote != tested_sha:
        raise ValueError('Tested source was superseded; refusing promotion')

    with tempfile.TemporaryDirectory(prefix='tasks-promotion-') as directory:
        candidate = Path(directory) / 'candidate'
        git(repo, 'worktree', 'add', '--detach', str(candidate), tested_sha)
        try:
            path = candidate / OVERLAY
            path.write_text(update_tags(path.read_text(), tag))
            subprocess.run([sys.executable, '-B', str(candidate / 'scripts/validate-deployment.py')],
                           cwd=candidate, check=True)
            if git(candidate, 'status', '--porcelain', '--untracked-files=all') != 'M ' + OVERLAY:
                raise ValueError('Unexpected changes outside the image overlay')
            git(candidate, 'add', '--', OVERLAY)
            git(candidate, '-c', 'user.name=github-actions[bot]', '-c',
                'user.email=41898282+github-actions[bot]@users.noreply.github.com',
                'commit', '-m', f'chore(deploy): promote tasks-app {tag}')
            latest = git(repo, 'ls-remote', '--exit-code', 'origin', 'refs/heads/main').split()[0]
            if latest != tested_sha:
                raise ValueError('Tested source was superseded before push')
            # A later race is rejected by normal fast-forward/ref-lock checks.
            # Never rebase or force a stale image choice over newer source.
            git(candidate, 'push', 'origin', 'HEAD:refs/heads/main')
            print(f'Promoted tasks-app {tag}')
        finally:
            git(repo, 'worktree', 'remove', '--force', str(candidate))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_dir', type=Path)
    parser.add_argument('tested_sha')
    parser.add_argument('--check-build', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}', args.tested_sha):
        raise ValueError('Expected full tested commit SHA')
    repo = Path(git(args.source_dir, 'rev-parse', '--show-toplevel'))
    if git(repo, 'rev-parse', 'HEAD') != args.tested_sha:
        raise ValueError('Source checkout differs from tested revision')
    if git(repo, 'status', '--porcelain', '--untracked-files=all'):
        raise ValueError('Source checkout must be clean')
    if args.check_build:
        print('build=' + str(requires_build(repo, args.tested_sha)).lower())
    else:
        promote(repo, args.tested_sha)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, subprocess.CalledProcessError, yaml.YAMLError) as exc:
        print(f'Promotion refused: {exc}', file=sys.stderr)
        sys.exit(1)
