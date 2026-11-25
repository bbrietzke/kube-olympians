# MiroTalk C2C: two-person video calls

[MiroTalk C2C](https://github.com/miroslavpejic85/mirotalkc2c) (v1.5.10, AGPL-3.0) at **https://video.brietzke.me**. Open the page, pick a room name, and share the link; the other person joins in their browser. **Experimental.**

| Task | Command (from `brietzke-video/`) |
| --- | --- |
| Deploy / apply config changes | `make olympians` (generates `base/mirotalk.env` first; restarts the pod) |
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
- `base/mirotalk.env` (git-ignored, generated) holds `API_KEY_SECRET`, which guards the REST API (`POST /api/v1/meeting`, `/api/v1/join`; header `authorization`).
- **Image:** upstream publishes only `:latest`, so `base/mirotalk.yaml` pins it by digest. To update, look up the new digest (`docker buildx imagetools inspect mirotalk/c2c:latest`), change it, and run `make olympians`.

## Access
**One shared login (HTTP basic auth),** checked by Traefik before anything reaches MiroTalk. It's in `base/basic-auth.yaml`, a Traefik Middleware attached to the HTTPRoute. Send it to whoever you're calling. Browsers remember it for the session, including for the Socket.IO WebSocket.

| Task | Command (from `brietzke-video/`) |
| --- | --- |
| Show the login | `make password` |
| Change it | edit `base/basic-auth.env`, then `make olympians` (it re-hashes because the file is newer) |

- **What lives where:** `base/basic-auth.env` (git-ignored, generated) holds the plaintext. Only a bcrypt hash goes into the cluster, as Secret `mirotalk-basic-auth` built from `base/basic-auth.htpasswd` (git-ignored). `removeHeader: true` strips the `Authorization` header, so MiroTalk never sees the password.
- **It's a shared password.** Anyone you give it to can keep using it until you change it. Changing it is quick, but it locks everyone out until they get the new one.
- **It's only as private as the TLS around it.** Basic auth sends the password with every request, protected by HTTPS between the browser and Cloudflare. Cloudflare decrypts it at its edge, and it travels the tunnel to Traefik.
- **Stronger option:** a Cloudflare Access application on `video.brietzke.me` with a per-email one-time-PIN policy. It's per person, revocable, and enforced at Cloudflare's edge before the tunnel. The two can be stacked.

**Tested 2026-11-24 from outside:** without the login, the page, its assets and the WebSocket all get `401`, and a wrong password also gets `401`. With the login, the page returns 200, the Socket.IO WebSocket upgrade returns `101`, only `https://video.brietzke.me` gets a CORS allow-origin, and `/client-config` lists only the STUN server.
