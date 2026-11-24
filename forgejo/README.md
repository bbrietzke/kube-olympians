# Forgejo — Git Forge, Actions Runners and GitHub Mirrors

[Forgejo](https://forgejo.org/) runs in the `forgejo` namespace at **https://git.faultycloud.xyz**. It has its own CI, Forgejo Actions, which uses GitHub-Actions-compatible workflows and runs them on two in-cluster runners. It can also keep **pull mirrors of GitHub repositories**.

| Task | Command (from `forgejo/`) |
| --- | --- |
| Install or upgrade Forgejo | `make helm` (runs `prerequisites` first) |
| Deploy or refresh the runners | `make runners` |
| Initial admin login | `make password` (username `forgejo-admin`) |
| Remove (keeps data) | `make uninstall-helm` |

## Design

| Part | Choice |
| --- | --- |
| Version | forgejo-helm chart **17.3.3**, which ships Forgejo **15.0.12**, the **LTS** line, supported until 2027-07-15. The image is rootless and multi-arch; it runs amd64 here. |
| Web UI | HTTPRoute `forgejo` on `traefik-gateway`. TLS (wildcard certificate) and the HTTP→HTTPS redirect happen at the Gateway. |
| Git over SSH | Service `forgejo-ssh`, a LoadBalancer on **192.168.3.201:22** (Cilium LB IPAM, pinned with `lbipam.cilium.io/ips`), forwarding to the container's port 2222. Clone URLs use **`git-ssh.faultycloud.xyz`**, because the LAN wildcard `*.faultycloud.xyz` points at Traefik (`.200`), which doesn't serve SSH. That name needs its own DNS record: `address=/git-ssh.faultycloud.xyz/192.168.3.201` in dnsmasq (more specific than the wildcard, so it wins). |
| Database | `forgejo` database in CloudNativePG **cluster00**, through a `DatabaseRole` and a `Database` (`base/`). Covered by cluster00's snapshot and B2 backups. cluster00 itself is not modified. |
| Repositories, attachments | 20Gi `rook-ceph-ssd` PVC `gitea-shared-storage` (kept on uninstall). SSD rather than the default SMR HDD class, because git does lots of small random I/O. |
| Cache / sessions / queue | Memory cache, sessions in the database, LevelDB queue. No Redis, because it's a single replica. |
| Accounts | `DISABLE_REGISTRATION: true`, so the admin creates users. The admin is created once (`passwordMode: initialOnlyNoReset`), so a password changed in the UI sticks. |
| Packages | Off. Container images go to Harbor. |
| Actions | On. `uses:` without a URL resolves against `https://data.forgejo.org`, Forgejo's mirror of common actions such as `actions/checkout`. |
| Migrations | Only from GitHub (`ALLOWED_DOMAINS`). Mirrors sync every 1h by default (minimum 10m). |

## Runners

`overlays/runners` runs two forgejo-runner **v13.2.2** pods (StatefulSet `forgejo-runner`), spread across workers. Each pod has:

- an **init container** that writes `config.yml` from `config.yml` (a ConfigMap) plus the pod's own pre-shared credentials (`forgejo-runner-0` uses `token-0`/`uuid-0`, and so on)
- the **runner**, which polls Forgejo at `http://forgejo-http.forgejo.svc:3000/`, the in-cluster address, so it doesn't depend on LAN DNS
- a **`docker:28-dind`** sidecar (privileged) that runs the job containers, one job at a time (`capacity: 1`), so jobs never share a daemon

**Labels** (all images multi-arch; jobs run on amd64):

| `runs-on:` | Image | For |
| --- | --- | --- |
| `docker`, `ubuntu-latest` | `node:22-bookworm` | Ordinary jobs and JavaScript actions (`actions/checkout`, …) |
| `docker-cli` | `docker:28-cli` | `docker build` / `docker run` / `docker push` against the pod's dind daemon (`DOCKER_HOST` and TLS certs are injected) |

Job containers share the pod's network (`network: host`). They reach dind on `localhost:2376` and resolve names through the cluster DNS, for example `git.faultycloud.xyz` and `harbor.faultycloud.xyz`.

**Registration is offline, with pre-shared secrets.**
1. `make prerequisites` generates `base/forgejo-runner.env` with one 40-hex secret per runner. Its UUID is the first 16 characters as hex-encoded ASCII.
2. `make runners` registers each secret inside the Forgejo pod with `forgejo forgejo-cli actions register --name forgejo-runner-N --secret …`, and checks that Forgejo returns the expected UUID.
3. It then applies the StatefulSet. Re-running it is safe.

To add a runner, add `token-2`/`uuid-2` to the env file (same derivation), add `2` to `RUNNERS` in the Makefile, raise `replicas`, and run `make prerequisites runners`.

**Pod Security.** Talos enforces Pod Security Admission, so the `forgejo` namespace is labeled `pod-security.kubernetes.io/enforce=privileged` (`base/namespace.yaml`). Without it the runner pods are rejected.

**Security.** The dind sidecar is privileged, so a job can reach the node it runs on. That's acceptable only because Forgejo has no open registration and only trusted users can push. Don't open registration, and don't run workflows from untrusted forks.

## Example workflow

`example/.forgejo/workflows/ci.yaml` has two jobs:
- `hello` (`docker`) runs `actions/checkout@v4` and prints the arch and Node version.
- `image` (`docker-cli`) builds an image on dind, runs it, and pushes it to Harbor when the `HARBOR_USERNAME` / `HARBOR_PASSWORD` Actions secrets (a Harbor robot account) are set.

Copy it into a repository as `.forgejo/workflows/ci.yaml`. Forgejo also reads `.github/workflows/` if there's no `.forgejo/` directory.

**Tested on the demigods cluster (arm64) on 2026-11-22** in a private test repo, `forgejo-admin/ci-test`:
- Pushing the workflow triggered it, and both jobs succeeded on `forgejo-runner-0`.
- `hello` checked out the commit from `data.forgejo.org`'s `actions/checkout@v4` on `aarch64` (Node v22.23.5). It took about 90 seconds, most of it pulling `node:22-bookworm` the first time.
- `image` built and ran an image on dind (`built by forgejo-runner on aarch64`) and skipped the push, since no Harbor secrets were set.

## GitHub pull mirrors

In the UI: **+ → New Migration → GitHub**, then enter the repository URL. For private repos, add a GitHub token with read access to that repo. Tick **"This repository will be a mirror"**. Through the API:

```sh
curl -u forgejo-admin:<password> -H 'Content-Type: application/json' \
  -X POST https://git.faultycloud.xyz/api/v1/repos/migrate -d '{
    "clone_addr": "https://github.com/<owner>/<repo>.git",
    "repo_name": "<repo>", "repo_owner": "forgejo-admin",
    "service": "github", "mirror": true, "mirror_interval": "1h", "private": true
  }'   # add "auth_token": "<github token>" for a private repository
```

- **Syncing:** a mirror syncs on its interval, and **Settings → Synchronize Now** forces a sync.
- **Mirrors are read-only.** Push changes to GitHub.
- **Pull mirrors can only be created as new repositories.** An existing repo can't be turned into one.

**Tested on demigods:** `github.com/bbrietzke/kube-demigods` was mirrored as `forgejo-admin/kube-demigods`. Its latest commit matched GitHub (`2cdfc0c`), and it cloned over HTTPS from the LAN.

## Credentials

`make prerequisites` creates these git-ignored files with random values if they're missing. The `*.env.example` files show their format.

| File | Secret(s) | Used by |
| --- | --- | --- |
| `base/forgejo-db.env` | `forgejo-db-credentials` (`db`), `forgejo-database` (`forgejo`) | CNPG `DatabaseRole`; Forgejo's `FORGEJO__DATABASE__PASSWD` |
| `base/forgejo-admin.env` | `forgejo-admin` | The chart's initial admin. The username can't be `admin`. |
| `base/forgejo-runner.env` | `forgejo-runner` | Runner registration and the runner config |

The database role's first reconcile fails for about 30 seconds (`secrets ... is forbidden`) while the operator grants access to its Secret. `make prerequisites` waits it out, as in the harbor component.

## Uninstalling

`make uninstall-helm` removes the runners and the release. It **keeps**:
- the repository PVC
- the `forgejo` namespace and its Secrets
- the `forgejo` database and role in cluster00 (both `retain`)

To remove everything for good:

```sh
kubectl delete namespace forgejo
kubectl -n db exec cluster00-1 -c postgres -- psql -U postgres -c 'DROP DATABASE forgejo'
kubectl -n db delete database forgejo
```

Then set `ensure: absent` in `base/database-role.yaml`, run `make prerequisites`, and finally `kubectl -n db delete databaserole forgejo`.
