# Tasks application

Application source, tests, Dockerfiles, Kubernetes manifests and image release automation.

## Development

Install Bun 1.3.10 and Node.js 22 or newer. Bun manages dependencies and runs
workspace scripts; Node.js runs the API and Node-based development tools.

```sh
bun install --frozen-lockfile
bun run validate
```

The monorepo contains `apps/api` and `apps/web`. Start their development servers
in separate terminals:

```sh
bun run dev:api
bun run dev:web
```

Use the Docker Compose configuration for local services and configure the root
`.env` file before starting the API. Do not commit real provider credentials or
local environment secrets.

Use `bun run test` to run the existing Vitest suites. The other checks are
`bun run check`, `bun run typecheck`, and `bun run build`.

Commit `bun.lock` when dependencies change. CI and Docker builds use
`bun install --frozen-lockfile` for reproducible installs. Keep the Bun version in
`package.json`, `.github/workflows/ci.yml`, and both Dockerfiles in sync.

## Deployment ownership

Application deployment desired state is colocated here:

- `argocd/tasks-app/`: the existing Argo Application definition.
- `deploy/base/`: workload resources.
- `deploy/overlays/homelab/`: environment settings, mesh patches and image tags.

Cluster infrastructure, the shared Istio gateway, registration and permission
boundaries remain in `avjpl/home-lab`. The Application identity stays
`argocd-app-tasks-app/tasks-app`, targeting namespace `tasks-app`.

Validate deployments with Python 3.12+, PyYAML and kubectl:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-deployment.txt
.venv/bin/python -B -m unittest discover -s tests/deployment
.venv/bin/python -B scripts/validate-deployment.py
kubectl kustomize deploy/overlays/homelab
```

Argo watches main directly: deployment PR checks must pass before merge. Keep
Namespace and PVC identities intact; never empty the watched path to pause Argo.

## Istio scope

Only API/web Pod templates opt into injection. MongoDB and Redis remain unmeshed,
and the namespace has no injection label. The overlay allows API/web egress to
Istiod TCP 15012 before injection. Native sidecars appear in `initContainers` with
`restartPolicy: Always`. Each proxy requests 100m CPU / 128Mi and is limited to
500m / 256Mi; startup waits for proxy readiness. Rollouts use zero unavailable,
one surge and ten seconds of minimum readiness.

Gateway-to-API/web uses automatic mTLS with permissive inbound policy. Database
connections are outside mesh mTLS. For mesh rollback remove the relevant overlay
patch one Deployment at a time; keep Istiod egress until injected Pods are gone.
Validate task reads/cache behavior and destination `mutual_tls` metrics, not just
the dependency-independent `/api/health` endpoint. Preserve database Pods/PVCs.

## Continuous delivery

The workflow in `.github/workflows/release.yml` runs after successful CI for a
push to `main` in this repository:

1. **Check out the tested commit** using `actions/checkout`.
2. **Publish API and web images** to GHCR using Docker actions. The metadata
   action generates a shared tag from the first 12 characters of the tested
   commit SHA.
3. **Check that the release is current** using `actions/github-script`. If a
   newer commit is already on `main`, the workflow stops before updating deployment.
4. **Check out the deployment repository** using `actions/checkout` and the
   existing `DEPLOYMENTS_SSH_KEY` secret.
5. **Update the two image tags** in
   `applications/tasks-app/overlays/homelab/kustomization.yaml` using `mikefarah/yq`.
6. **Commit and push that file** using `stefanzweifel/git-auto-commit-action`.
   Argo CD detects the change and deploys the new images automatically.

`DEPLOYMENTS_SSH_KEY` must have write access to `avjpl/application-deployments`.
The source repository's `GITHUB_TOKEN` is used for GitHub API access and publishing
images to GHCR; it does not write to the deployment repository.

Release runs are serialized. A conflicting update to the deployment repository
causes the push to fail rather than retry or force-push. Rerun the failed release
job from the GitHub Actions UI if the tested commit is still current on `main`.
If it has been superseded, use the newer commit's successful CI release instead.
