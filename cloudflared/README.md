# cloudflared: public access through Cloudflare Tunnel

Publishes selected apps at `*.brietzke.me` without opening ports on the router or publishing the home IP. Cloudflare's edge terminates HTTPS, and the `cloudflared` connector carries requests into the cluster over outbound-only connections.

```
internet ─► Cloudflare ─► cloudflared (2 replicas) ─► traefik-internal:80 (ClusterIP, entrypoint "public" :8100)
                                                        └─► Gateway traefik-public   *.brietzke.me    ← public apps
LAN ─► 192.168.3.200 (Cilium LB) ─► traefik :80/:443 (entrypoints web/websecure)
                                      └─► Gateway traefik-gateway  *.faultycloud.xyz ← LAN apps (unchanged)
```

## Keeping internal apps private
- **The tunnel can only reach one Gateway.** `cloudflared` connects to the `public` entrypoint, which is not on the LoadBalancer. Only `traefik-public` has listeners on that port, so a request through the tunnel can never match a route attached to `traefik-gateway`, whatever `Host` header it carries.
- **Opt-in, in two deliberate steps.** `traefik-public` accepts routes only from namespaces labeled `olympians/exposure=public`, and the route must name it in `parentRefs`.
- **Visitor IPs.** The `public` entrypoint trusts `X-Forwarded-*` from the pod CIDR `10.254.0.0/22`, so apps see the visitor's address and `X-Forwarded-Proto: https`. `CF-Connecting-IP` is also passed through.

## Exposing an app
```sh
kubectl label namespace <ns> olympians/exposure=public
```
```yaml
spec:
  parentRefs: [{name: traefik-public, namespace: traefik}]
  hostnames: ["app.brietzke.me"]
```

**To serve an app on both networks,** list both Gateways and both hostnames in one HTTPRoute, and label the namespace for both Gateways. Each Gateway serves only the hostnames that match its own listeners. `overlays/whoami` is a working example. This suits stateless apps. Apps with a single configured base URL (Forgejo's `ROOT_URL`, Harbor's `externalURL`, OAuth redirect URIs) will redirect or break on the second name. Give them one canonical hostname instead.

## Cloudflare setup (once, by hand)
The tunnel is **remotely managed**: its routes live in Cloudflare, not in this repo. A wildcard rule means they rarely change.

1. Dashboard → **Networking → Tunnels → Create a tunnel** → type **Cloudflared**, name `olympians` (tunnel ID `1591f6b5-7f71-4587-99f1-b91953db595c`).
2. Copy the token from the install command (the long `eyJ…` string after `--token`; not the tunnel ID):
   Store it in Bitwarden Secrets Manager as `cloudflared/cloudflared-tunnel-token/TUNNEL_TOKEN`, in the `olympians` project. The `cloudflared-tunnel-token` ExternalSecret brings it into the cluster.
   This is separate from cert-manager's DNS-01 token. Don't reuse either one for the other. To check it's the right token without printing it, decode it: its `"t"` field is the tunnel ID.
3. **Networking → Tunnels → `olympians` → Routes tab → Add route → Published application**, twice. Both use **Service URL** `http://traefik-internal.traefik.svc.cluster.local:80`:
   - **Subdomain** blank, **Domain** `brietzke.me`
   - **Subdomain** `*`, **Domain** `brietzke.me`. Cloudflare's docs don't mention wildcards; if the form refuses `*`, add one route per public name instead.
4. **DNS → Records** for `brietzke.me`: check that proxied CNAMEs `brietzke.me` and `*` (or each public name) → `1591f6b5-7f71-4587-99f1-b91953db595c.cfargotunnel.com` exist, and add any that are missing. Remove older `A`/`AAAA`/`CNAME` records for those names first, or they will conflict.

Symptom of missing routes: every request gets an empty `503`, and the connector logs `No ingress rules were defined … cloudflared will return 503`.

Cloudflare's Universal SSL certificate covers `brietzke.me` and `*.brietzke.me` (one level only: `a.b.brietzke.me` would need Advanced Certificate Manager).

## Targets
| Target | What it does |
|---|---|
| `make -C traefik postCertManager` | Adds the `public` entrypoint and the `traefik-internal` Service, then applies the `traefik-public` Gateway (`make -C traefik public` on its own) |
| `make -C cloudflared olympians` | Deploys the connector and its token ExternalSecret. Needs `external-secrets`. After changing the token in Bitwarden, also run `kubectl -n cloudflared rollout restart deployment/cloudflared`. |
| `make -C cloudflared whoami` | Test app at `whoami.brietzke.me` (via the tunnel) and `whoami.faultycloud.xyz` (LAN) |
| `make -C cloudflared uninstall-whoami` / `uninstall` | Remove the test app / the connector. The tunnel and its routes stay in Cloudflare. |

## Testing
```sh
curl -s https://whoami.brietzke.me                      # from outside (phone off Wi-Fi): shows X-Forwarded-For = your public IP
curl -s https://whoami.faultycloud.xyz                  # on the LAN
# Internal routes must not be reachable through the tunnel's entrypoint:
kubectl -n cloudflared run probe --rm -it --image=curlimages/curl:8.17.0 --restart=Never -- \
  curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: harbor.faultycloud.xyz' http://traefik-internal.traefik.svc/   # expect 404
```
`kubectl -n cloudflared logs deploy/cloudflared` should show four `Registered tunnel connection` lines per replica.
