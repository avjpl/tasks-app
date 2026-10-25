# Tasks application

Application source, tests, Dockerfiles and image release automation.

## Development

```sh
npm ci
npm run validate
```

The monorepo contains `apps/api` and `apps/web`. Use the existing development
commands and Docker Compose configuration for local development. Do not commit
real provider credentials or local environment secrets.

## Deployment ownership

Argo CD and Kubernetes manifests are maintained in the private
[application-deployments](https://github.com/avjpl/application-deployments) repository:

- `argocd/tasks-app/`: the existing Argo Application definition.
- `applications/tasks-app/base/`: workload resources.
- `applications/tasks-app/overlays/homelab/`: environment settings and image tags.

The old `argocd/` and `k8s/` paths were removed only after Argo switched successfully
to the new source, preserving the workload namespace and PVC identities. Cluster
infrastructure and permission boundaries remain in `avjpl/home-lab`.

## Continuous delivery

Successful CI on main builds the exact tested commit into GHCR images. The release
workflow uses `DEPLOYMENTS_SSH_KEY`, scoped to the deployment repository, to update
only the two image selections in its homelab overlay. Argo CD then deploys those
versions. The source repository's `GITHUB_TOKEN` does not write another repository.

Promotion rejects superseded source commits and dirty deployment checkouts, retries
concurrent deployment edits without force-pushing, and preserves unrelated changes.
Run its offline tests with:

```sh
python3 -B -m unittest discover -s tests/deployment
```

Migration status: source handoff is verified and the release workflow is enabled.
Successful main-branch CI now promotes tested images into application-deployments.
