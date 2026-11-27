# MiroTalk C2C: two-person video calls

[MiroTalk C2C](https://github.com/miroslavpejic85/mirotalkc2c) (v1.5.10, AGPL-3.0) at **https://video.brietzke.me**. Open the page, pick a room name, and share the link; the other person joins in their browser. **Experimental.**

| Task | Command (from `brietzke-video/`) |
| --- | --- |
| Deploy / apply config changes | `make olympians` (waits for its ExternalSecret; restarts the pod) |
| Remove | `make uninstall` (nothing is stored, so nothing is lost) |

## How it works
- **This pod** serves the web app and the Socket.IO **signaling**, WebSocket only, through Cloudflare → cloudflared → `traefik-public`. That's how the two browsers find each other.
- **Audio and video go browser to browser** (WebRTC), not through the cluster or Cloudflare. Each browser finds its public address with Google's public STUN server (`stun.l.google.com:19302`).
- **There's no TURN server yet.** Most calls connect directly. Calls where **both** sides are behind strict (symmetric) NAT, which is common on mobile carriers and some corporate networks, will fail to connect media. coturn can't run behind the tunnel: it needs UDP at a public IP. The options are an in-cluster coturn with router port forwards and a non-proxied `turn.brietzke.me` (exposes the home IP), coturn on a VPS, or Cloudflare's managed TURN. To use one, set the `TURN_SERVER_*` keys in `base/config.yaml`.
- **One replica** with `Recreate`: rooms live in the process's memory, so both people in a call must reach the same pod. Restarting it drops calls in progress.

## Configuration
- `base/config.yaml` holds the settings, as environment variables; the full list is in [upstream's `.env.template`](https://github.com/miroslavpejic85/mirotalkc2c/blob/main/.env.template).
- **The image bakes in `.env.template`**, and the app loads it without overriding variables set here. Anything not set falls back to the template, which **enables TURN with a shared metered.ca account**. That's why `TURN_SERVER_ENABLED: "false"` is set explicitly, along with the survey, ngrok, email, Sentry and Mattermost defaults.
- `CORS_ORIGIN` must be a **JSON list** (`'["https://video.brietzke.me"]'`). A bare URL fails to parse, and the app logs `Error parsing CORS_ORIGIN` and allows every origin.
- `API_KEY_SECRET` (Bitwarden `mirotalk/mirotalk-secrets/API_KEY_SECRET`, from Bitwarden Secrets Manager (`external-secrets/`)) which guards the REST API (`POST /api/v1/meeting`, `/api/v1/join`; header `authorization`).
- **Image:** upstream publishes only `:latest`, so `base/mirotalk.yaml` pins it by digest. To update, look up the new digest (`docker buildx imagetools inspect mirotalk/c2c:latest`), change it, and run `make olympians`.

## Access
**Logins go through Pocket ID** (`brietzke-auth`, https://auth.brietzke.me) using MiroTalk's own OIDC support. Traefik does no authentication here.

- **Creating a room requires a login.** Opening `/` redirects to Pocket ID, where you sign in with your passkey and are sent back.
- **Guests join without an account,** but only a room that already exists: `/?room=<name>` and `/join?room=<name>&name=<who>` work once you're in the room. Asking for a room that doesn't exist sends a guest to the login (`/`), or returns MiroTalk's "not found" JSON for `/join`. MiroTalk sends that JSON with status 200.
- **Use room names that are hard to guess.** Anyone who knows the name of a room in progress can join it.
- **Settings:** `OIDC_*` in `base/config.yaml`. `OIDC_AUTH_REQUIRED: "false"` is what lets guests join. Set it to `"true"` to require a login from everyone. `OIDC_AUTH_LOGOUT: "false"`, because `true` calls Auth0's logout endpoint, which Pocket ID doesn't have.
- **Client credentials:** the Pocket ID client "MiroTalk" is confidential, with callback `https://video.brietzke.me/auth/callback`. MiroTalk also sends PKCE (S256). Its ID and secret are in Bitwarden (`mirotalk/mirotalk-secrets/OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET`), next to `API_KEY_SECRET` and `SESSION_SECRET`. After changing any of them in Bitwarden, run `make olympians`: ESO syncs the Secret, but only a restart makes MiroTalk read it.
- **Pocket ID must be up** for anyone to create a room. Guests joining an existing room don't need it.

**Tested 2026-11-25 from outside, not logged in:**
- `/` redirects (`302`) to `https://auth.brietzke.me/authorize` with the MiroTalk client, callback and PKCE.
- `/?room=<nonexistent>` redirects to the login, and `/join` for a room that doesn't exist returns the not-found JSON.
- Static assets return `200` and the Socket.IO WebSocket upgrade `101`; guests need both.
- Earlier tests still hold: CORS allows only `https://video.brietzke.me`, and `/client-config` lists only the STUN server.
