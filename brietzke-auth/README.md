# Pocket ID: login for brietzke.me apps

[Pocket ID](https://github.com/pocket-id/pocket-id) v2.19.3 at **https://auth.brietzke.me** is the OpenID Connect (OIDC) provider for apps on `brietzke.me`. Logins use **passkeys only**; there are no passwords. Apps log users in themselves over OIDC, and Traefik only routes.

| Task | Command (from `brietzke-auth/`) |
| --- | --- |
| Deploy, or apply config changes | `make olympians` (generates the secrets; no public route) |
| Make it public | `make publish` (first time: claim the admin at once, see below) |
| Take it offline (keeps running) | `make unpublish` |
| Remove (keeps the database) | `make uninstall` |

## Design

| Part | Choice |
| --- | --- |
| Image | `ghcr.io/pocket-id/pocket-id:v2.19.3-distroless`, pinned by digest. Runs as UID 65532 with a read-only root filesystem, and has no shell. |
| Data | The `pocketid` database in CloudNativePG **cluster00**, through a `DatabaseRole` and a `Database` in `base/database.yaml` (the same pattern as harbor and forgejo). `FILE_BACKEND=database` puts uploads there too, so the pod keeps no state, and users, passkeys and clients are covered by cluster00's snapshot and B2 backups. |
| Exposure | The HTTPRoute is on `traefik-public` (Cloudflare tunnel), in `overlays/public`, separate from the rest. |
| Client IPs | `TRUST_PROXY=10.254.0.0/22` (Traefik is a pod) and `TRUSTED_PLATFORM=CF-Connecting-IP` |
| Settings | Environment variables in `base/config.yaml`. Everything under "Application Configuration" (signups, SMTP, session length) is set in the admin UI and stored in the database. |
| Email | None configured. Add users in the admin UI and send them the one-time setup link it generates. |

**Secrets** come from Bitwarden Secrets Manager (`external-secrets/`) through ExternalSecrets (`base/external-secrets.yaml`):
- `db/pocketid-db-credentials/password`: the PostgreSQL login. It feeds both the role's Secret and Pocket ID's `DB_CONNECTION_STRING`, which a template builds, so the two can't drift apart.
- `pocket-id/pocket-id-secrets/ENCRYPTION_KEY`.
- **`ENCRYPTION_KEY` is now kept off the cluster** in Bitwarden. It encrypts Pocket ID's token-signing keys in the database. Without it, a restored database can't sign tokens, and every client and session breaks.

**First install:** the pod restarts a few times (`failed to ping Postgres database`) until CloudNativePG has created the role, about 30 seconds. It then stays up.

## First-time setup (done 2026-11-25)
Until the first account exists, **`/setup` lets anyone create the admin**. That's why the route is a separate step.
1. `make publish`.
2. Immediately open https://auth.brietzke.me/setup, then enter your username, email and name, and **Add Passkey**.

## Adding an app (OIDC client)
In the admin UI, go to OIDC clients and create a new client:
- **Callback URL:** the app's exact redirect URL. Only `https://` is allowed (`ALLOW_INSECURE_CALLBACK_URLS=false`).
- **Confidential** (with a secret) for anything that logs in from a server: MiroTalk, a Go backend, ASP.NET Core.
- **Public** with PKCE for code that runs entirely on the user's device: single-page apps, mobile apps, CLIs.
- **Allowed user groups** (optional): restrict the client to certain users.

Put the client ID and secret in the app's own git-ignored env file, never in git.

Apps need these settings:
- issuer `https://auth.brietzke.me`, discovered from `/.well-known/openid-configuration`
- scopes `openid profile email`, plus `groups` for group claims

**Go:**
```go
provider, _ := oidc.NewProvider(ctx, "https://auth.brietzke.me")   // github.com/coreos/go-oidc/v3
cfg := oauth2.Config{ClientID: id, ClientSecret: secret, Endpoint: provider.Endpoint(),
    RedirectURL: "https://myapp.brietzke.me/callback", Scopes: []string{oidc.ScopeOpenID, "profile", "email"}}
```

**ASP.NET Core:** `AddAuthentication().AddCookie().AddOpenIdConnect(o => { o.Authority = "https://auth.brietzke.me"; ... })`.

**Apps with no OIDC support:** put oauth2-proxy in front of them, as its own Deployment or a sidecar, so authentication stays out of Traefik. Or use a Cloudflare Access application.

## Clients
| App | Callback | Type |
| --- | --- | --- |
| MiroTalk C2C (`brietzke-video`) | `https://video.brietzke.me/auth/callback` | confidential (MiroTalk also sends PKCE) |

## Uninstalling
`make uninstall` removes the route and Pocket ID. It keeps the `pocketid` database and role in cluster00 (both `retain`). To remove them for good:
```sh
kubectl -n db exec cluster00-1 -c postgres -- psql -U postgres -c 'DROP DATABASE pocketid'
kubectl -n db delete database pocketid
```
Then set `ensure: absent` in `base/database.yaml`, run `make olympians`, and finally run `kubectl -n db delete databaserole pocketid`.
