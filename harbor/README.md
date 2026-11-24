# Harbor — Container Registry

[Harbor](https://goharbor.io/) is the cluster's private container and Helm-chart registry, with vulnerability scanning (Trivy). It runs in the `harbor` namespace at **https://harbor.faultycloud.xyz**.

| Task | Command (from `harbor/`) |
| --- | --- |
| Install or upgrade | `make helm` (runs `prerequisites` first) |
| Admin password (user `admin`) | `make password` |
| Remove the release (keeps data) | `make uninstall-helm` |

## Design

| Part | Choice |
| --- | --- |
| Chart / version | `goharbor/harbor` chart **1.19.4**, with every image overridden to Harbor **v2.16.0** |
| Exposure | `expose.type: route`: an HTTPRoute `harbor-route` on `traefik-gateway`. TLS ends at the Gateway (wildcard `*.faultycloud.xyz` certificate), and HTTP is redirected to HTTPS there. |
| Database | The `harbor` database in CloudNativePG **cluster00** (`db` namespace), so it's covered by cluster00's snapshot and Backblaze B2 backups |
| Cache / job queue | Harbor's internal Valkey (StatefulSet, 1Gi `rook-ceph-hdd`) |
| Image layers | 100Gi `rook-ceph-hdd` PVC (`harbor-registry`, filesystem storage) |
| Other volumes | Job logs 1Gi, Trivy DB 5Gi, all `rook-ceph-hdd` (the default class) |
| Scanner | Trivy, enabled |

**Why v2.16.0 images on a 2.15 chart.**
- The olympians nodes are amd64, so the chart's default 2.15.4 would also run. 2.16.0 keeps Harbor on the same version as the demigods (arm64) cluster, where 2.16.0 (2026-11-10) is the first release with arm64 images.
- Chart 1.19.4 is the newest released chart. When goharbor ships a chart for 2.16, switch `CHART_VERSION` to it and drop the `tag: v2.16.0` overrides in `helm/values.yaml`.
- Open upstream issue #24445, where Valkey crashes on 64k-page kernels, does not apply here: amd64 nodes use 4k pages.

**Database connections.** `cluster00` allows 100 connections in total, shared with everything else. `helm/values.yaml` caps Harbor at `maxOpenConns: 30` and `maxIdleConns: 5` per component, down from the chart's 900 and 100.

## Prerequisites

1. `postgresql` with `cluster00` running (`make -C postgresql olympians`).
2. `traefik` with the wildcard listeners (`make -C traefik postCertManager`).
3. **DNS:** `harbor.faultycloud.xyz` must resolve to the Gateway, `192.168.3.200`, on the LAN. That includes **the nodes themselves**, because containerd pulls images by that name. Add it on OpenWRT (DHCP and DNS → Hostnames, or `address=/harbor.faultycloud.xyz/192.168.3.200` in dnsmasq). Until then, only clients with an `/etc/hosts` entry can reach Harbor.

## How `make prerequisites` sets it up

1. It generates two git-ignored password files, if they don't exist, with 27 random characters each:
   - `base/harbor-db.env`: the PostgreSQL login for the `harbor` role.
   - `base/harbor-admin.env`: Harbor's initial admin password.
   The `*.env.example` files show their format.
2. It applies `overlays/olympians`:
   - the `harbor` namespace, labeled `olympians/traefik-gateway=allowed` so its HTTPRoute can attach to the Gateway
   - the Secrets `harbor-db-credentials` (`db` namespace, basic-auth, read by CloudNativePG), `harbor-database` and `harbor-admin` (`harbor` namespace, read by the chart)
   - a CNPG **`DatabaseRole`** named `harbor` (`base/database-role.yaml`): the login role, with its password from `harbor-db-credentials` and `databaseRoleReclaimPolicy: retain`
   - a CNPG **`Database`** named `harbor`, owner `harbor`, with `databaseReclaimPolicy: retain`
3. It waits until the DatabaseRole reports `applied` with **no error message**, then until the Database is applied.

### The role and database live outside cluster00's spec

Both use [declarative role management](https://cloudnative-pg.io/docs/1.30/declarative_role_management/) through separate `DatabaseRole` and `Database` objects in the `db` namespace, each referencing `cluster: {name: cluster00}`. The `cluster00` Cluster object, which the postgresql component owns, is never modified.

- **The first reconcile fails briefly.** On a fresh DatabaseRole, it reports `applied=false` with `secrets "harbor-db-credentials" is forbidden` for about 30 seconds. The operator first has to add that Secret to the instance's RBAC Role, and then CNPG retries and succeeds. That's why `make prerequisites` waits for `applied=true` **and** an empty message, not just `applied`.
- **A stale error can stick.** If a DatabaseRole ever shows `applied=true` with a leftover error message, metadata changes such as annotations don't trigger a new reconcile. A real spec change does, for example editing `comment` and re-running `make prerequisites`.
- **Rotating the password:** change `password=` in `base/harbor-db.env` and re-run `make prerequisites`. CNPG updates the role, but Harbor reads `harbor-database` only at startup, so restart `harbor-core` and `harbor-jobservice` afterwards.

## Using Harbor

```sh
make password                                     # admin password
docker login harbor.faultycloud.xyz -u admin
docker tag alpine:3 harbor.faultycloud.xyz/library/alpine:3
docker push harbor.faultycloud.xyz/library/alpine:3
```

The `library` project exists by default and is public, so the cluster can pull from it without credentials. For a private project, create a robot account in Harbor and use it as an image pull Secret:

```sh
kubectl -n <ns> create secret docker-registry harbor-pull \
  --docker-server=harbor.faultycloud.xyz --docker-username='robot$<name>' --docker-password=<token>
```

**Tested on olympians on 2026-11-23:**
- All eight components were healthy, including the database connection to cluster00. The API reported `v2.16.0`, and admin login worked.
- The portal served HTTPS with the `*.faultycloud.xyz` certificate, and HTTP redirected to HTTPS.
- A multi-arch `busybox:1.37` was copied into `library` with `skopeo copy --all` from an in-cluster pod. A pod on hera then pulled it through containerd with no credentials (amd64, 217 ms), so node DNS resolves `harbor.faultycloud.xyz`.
- A Trivy scan completed in under a minute.
- On first install, `harbor-jobservice` restarts once or twice ("no route to host" to `harbor-core`) until core is up. This is harmless.

**Tested on the demigods cluster on 2026-11-21:**
- All eight components were healthy, including the database connection to cluster00, and the portal served HTTPS with a valid certificate. HTTP redirected to HTTPS.
- Admin login worked, and the API reported `v2.16.0`.
- A multi-arch `busybox:1.37` was copied into `library` with `skopeo copy --all`, from a pod with a `hostAliases` entry for `harbor.faultycloud.app`, because node DNS wasn't set up yet. It read back as arm64 both with credentials and anonymously.
- A Trivy scan completed in about a minute.

The admin password in `base/harbor-admin.env` is only read the first time Harbor initialises its database. Change it later in the UI, and update the file to match for your own reference.

## Uninstalling

`make uninstall-helm` removes the release but **keeps the data**:
- the PVCs (`resourcePolicy: keep`)
- the `harbor` namespace and its Secrets
- the `harbor` database in cluster00 (`databaseReclaimPolicy: retain`)
- the `harbor` role

To remove Harbor for good:

```sh
kubectl delete namespace harbor
kubectl -n db delete database harbor                          # the database itself is retained
kubectl -n db exec cluster00-1 -c postgres -- psql -U postgres -c 'DROP DATABASE harbor'
```

Then remove the role. Set `ensure: absent` in `base/database-role.yaml` and re-run `make prerequisites`, so CNPG drops it, then `kubectl -n db delete databaserole harbor`. Deleting the DatabaseRole alone keeps the role in PostgreSQL (`retain`).
