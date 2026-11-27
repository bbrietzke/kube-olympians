# External Secrets: Kubernetes Secrets from Bitwarden

[External Secrets Operator](https://external-secrets.io) (chart pinned in `Makefile`) syncs Kubernetes Secrets from **Bitwarden Secrets Manager** (US cloud), so the secrets live off the cluster and off this laptop. **Work in progress**, on the `externalSecrets` branch.

| Task | Command (from `external-secrets/`) |
| --- | --- |
| Install / upgrade ESO + SDK server | `make helm` (runs `prerequisites`: namespace and the SDK server's TLS certificate). Needs `certificateManager` |
| Connect to Bitwarden | `make olympians` (machine account token from `base/bitwarden.env`, and the `bitwarden` ClusterSecretStore) |
| Copy the cluster-only Secrets into Bitwarden | `make rescue`, then `make rescue-done` once they're there |
| Remove | `make uninstall-helm` (synced Secrets stay) |

## How it's wired
| Piece | What |
| --- | --- |
| Bitwarden | organization `86103964-…6755`, project `6e97d616-…9055`, US cloud (`api.bitwarden.com`, `identity.bitwarden.com`). One project, so one store |
| Machine account | read-write on the project, as ESO's docs require (needed for PushSecret). Its access token is **the one bootstrap secret**: `base/bitwarden.env` (git-ignored) → Secret `external-secrets/bitwarden-access-token`. **Keep a copy in your Bitwarden password vault**: without it nothing can sync |
| `bitwarden-sdk-server` | ESO's chart runs Bitwarden's Rust SDK as a separate HTTPS service on :9998. Its certificate comes from a private CA in cert-manager (`overlays/prerequisites/sdk-server-tls.yaml`): self-signed → `bitwarden-sdk-ca` → `bitwarden-tls-certs`. There's no Cloudflare or ACME, so it works before any secret has synced |
| `ClusterSecretStore/bitwarden` | `base/cluster-secret-store.yaml`, usable from every namespace. It trusts the SDK server through `caProvider` (Secret `bitwarden-sdk-ca`, key `ca.crt`) |

All of it runs under PSA `restricted`. The SDK server runs as UID 65532, its image's own user.

## Naming in Bitwarden
One Bitwarden secret per Kubernetes Secret key, named **`<namespace>/<secret>/<key>`**, for example `db/backblaze-b2/ACCESS_KEY_ID`.

- ExternalSecrets look secrets up **by name** within the project. Bitwarden allows duplicate names, and a duplicate makes the lookup fail, so **keep names unique**. Renaming or copying a secret in the Bitwarden UI can break a sync.
- `dataFrom.find` doesn't filter on this provider yet: it returns every secret in the organization (ESO issue #6550). List keys one by one instead.

## The rescue (batch 1)
Seven Secrets exist **only in the cluster**, because their `.env` files are gone from disk. `overlays/rescue/pushsecrets.yaml` copies all 15 of their keys into Bitwarden:

| Secret | Keys |
| --- | --- |
| `cert-manager/cloudflare-api-token-secret` | `api-token` (DNS-01 for every certificate) |
| `db/backblaze-b2` | `ACCESS_KEY_ID`, `ACCESS_SECRET_KEY`. **The B2 key for cluster00's backups**: without it, a restore from B2 is impossible |
| `db/harbor-db-credentials`, `db/forgejo-db-credentials` | `password` (`harbor/harbor-database` and `forgejo/forgejo-database` hold the same values) |
| `harbor/harbor-admin` | `HARBOR_ADMIN_PASSWORD` |
| `forgejo/forgejo-admin` | `username`, `password` |
| `forgejo/forgejo-runner` | `token-0`, `uuid-0`, `token-1`, `uuid-1` |

`deletionPolicy: None` keeps the Bitwarden copies when `make rescue-done` deletes the PushSecrets.

**Done 2026-11-27:**
- All 15 keys were pushed, then read back through temporary ExternalSecrets, and every checksum matched the cluster's value.
- The components now read them back through ExternalSecrets.
- `make rescue-done` removed the PushSecrets, so nothing pushes and pulls the same value.

## What reads from Bitwarden
| Component | ExternalSecrets | Bitwarden secrets |
| --- | --- | --- |
| certificateManager | `cloudflare-api-token-secret` | `cert-manager/cloudflare-api-token-secret/api-token` |
| postgresql | `backblaze-b2` | `db/backblaze-b2/{ACCESS_KEY_ID,ACCESS_SECRET_KEY}` |
| harbor | `harbor-db-credentials` (db), `harbor-database`, `harbor-admin` | `db/harbor-db-credentials/password`, `harbor/harbor-admin/HARBOR_ADMIN_PASSWORD` |
| forgejo | `forgejo-db-credentials` (db), `forgejo-database`, `forgejo-admin`, `forgejo-runner` | `db/forgejo-db-credentials/password`, `forgejo/forgejo-admin/{username,password}`, `forgejo/forgejo-runner/{token,uuid}-{0,1}` |
| brietzke-auth | `pocketid-db-credentials` (db), `pocket-id-secrets` | `db/pocketid-db-credentials/password`, `pocket-id/pocket-id-secrets/ENCRYPTION_KEY` |
| brietzke-video | `mirotalk-secrets` | `mirotalk/mirotalk-secrets/{API_KEY_SECRET,SESSION_SECRET,OIDC_CLIENT_ID,OIDC_CLIENT_SECRET}` |
| cloudflared | `cloudflared-tunnel-token` | `cloudflared/cloudflared-tunnel-token/TUNNEL_TOKEN` |
| monitoring | `grafana-admin`, `alertmanager-pushover` | `monitoring/grafana-admin/{admin-user,admin-password}`, `monitoring/alertmanager-pushover/{user_key,token}` |

- **One value, several Secrets:** where an app needs its own copy of a DB password, both ExternalSecrets read the same Bitwarden secret, using `target.template` for the fixed `username` and the basic-auth type. The copies can't drift apart.
- **Taking over existing Secrets:** with `creationPolicy: Owner`, ESO adopted Secrets that kustomize had created, keeping their names and types. The values were checked unchanged before and after.
- **Install order:** cert-manager, then external-secrets, then everything that uses a Secret. The root Makefile does this.
- **Batch 2, 2026-11-27:** brietzke-auth, brietzke-video, cloudflared and monitoring.
  - Their `.env` files were first checked identical to the cluster, key by key, then pushed (11 keys).
  - Pocket ID's `DB_CONNECTION_STRING` is built by a template from the DB password instead of stored, and came out byte-for-byte identical.
  - The old hash-suffixed Secrets (`pocket-id-secrets-…`, `mirotalk-secrets-…`, `cloudflared-tunnel-token-…`) were deleted after the pods moved to the fixed-name ones.
- **Still to convert:** brietzke-cloud and brietzke-vault, on their branches.
- **Pods don't restart on a change.** Kustomize's hash suffix used to roll a Deployment when a secret changed. ESO updates the Secret in place, so apps that read env vars at start (Pocket ID, MiroTalk, cloudflared) need a restart. The first two Makefiles' `olympians` targets restart them; cloudflared needs `kubectl -n cloudflared rollout restart deployment/cloudflared`.

## Not covered
The Talos files in `../talos_olympians` (`talosconfig` and the machine configs, which hold the cluster's CA keys) aren't Kubernetes Secrets. Store them in Bitwarden by hand, for example as vault attachments.
