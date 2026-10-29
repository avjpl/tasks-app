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

1. Verify the tested revision is still current, then check out that exact commit.
2. Compare source/build inputs against the currently promoted source revision.
   Skip image builds for deployment/docs-only changes. Compare against the last
   promoted source, not the previous commit, so an outstanding source change is
   not lost behind a later manifest edit.
3. Publish API/web images tagged with the first 12 characters of the tested SHA.
4. Check out current main separately. `scripts/promote-colocated.py` validates a
   disposable candidate and changes only the two image tags in
   `deploy/overlays/homelab/kustomization.yaml`.
5. Push the promotion commit to this repository using `GITHUB_TOKEN`; Argo CD
   reconciles it. Stale source and concurrent pushes are rejected without rebasing
   or force-pushing. The caller's checkout is never rewritten.

Only the release job has contents/packages write permissions. Its bot push using
`GITHUB_TOKEN` does not trigger another push workflow, preventing recursive builds.
The candidate render is validated before push because that commit will not get
ordinary push CI. No cross-repository write key is required. Argo uses separate
read-only repository access.

Release runs are serialized. If a newer source revision supersedes a release,
use that revision's successful CI run. After a completed promotion, rerunning the
old workflow is rejected by the current-main guard; rerunning the promoter alone
is a no-op when the remote already selects that exact image pair.

Image rollback is a reviewed change to a known-good matching pair of tags. It is
not a database rollback. For source-location recovery restore the old manifest
path and exact platform permissions before switching the existing registration;
never recreate Applications, Namespace or database PVCs.
