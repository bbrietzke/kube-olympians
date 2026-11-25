# Cluster Components
Each component directory follows the same layout:

```
<component>/
  Makefile                 # run `make -C <component>` to list its targets
  base/                    # resources specific to this cluster (pools, storage classes, …)
  overlays/prerequisites/  # upstream CRDs and common resources, pinned by tag
  overlays/install/        # upstream operator or controller
  overlays/olympians/      # base/ plus cluster patches
  overlays/<extra>/        # backs an extra target (rook: toolbox; postgresql: snapshot, b2backup, plugin-barman-cloud)
  helm/                    # values files for the Helm route
  README.md                # day-two operations, where a component has them
```

Standard targets (only where the component supports them):

| Target | Purpose |
|---|---|
| `prerequisites` | CRDs and anything the install needs first |
| `install` | Kustomize install (runs `prerequisites` first) |
| `helm` | Helm install, an alternative to `install` |
| `olympians` | Apply this cluster's config from `base/` (works after either route) |
| `uninstall` / `uninstall-helm` | Tear down the matching route, in reverse order |

**Pick one route per component and stay on it.** Kustomize-installed objects carry `app.kubernetes.io/managed-by: kustomize`, and Helm refuses to adopt them ("invalid ownership metadata"). To switch a component from one route to the other, run its matching `uninstall` target first. Traefik should run from the Helm route, because `postCertManager` needs it. Cilium is Helm-only.

**Every target uses the `admin@olympians` context** (`KUBE_CONTEXT` in `common.mk`), whatever `kubectl config current-context` says. This kubeconfig also holds `admin@demigods`. Override it with `make … KUBE_CONTEXT=<name>`.

| Component | Version | prerequisites | install | helm | olympians | Extra |
|---|---|---|---|---|---|---|
| cilium | 1.20.5 | — | — | ✅ (Helm only) | `default-lb-pool` (192.168.3.200–204) + `lan0-l2` L2 announcements on `ens4f0` | `uninstall-olympians` |
| external-snapshotter | v8.7.0 | snapshot CRDs | snapshot-controller (kube-system) | no upstream chart | default `rook-ceph-snapclass` VolumeSnapshotClass | |
| rook | v1.21.2 | CRDs, common (namespace labeled PSA `privileged`), csi-operator | ✅ (upstream examples, patched) | ✅ (operator + cluster charts) | object store `s3` (500 GiB quota) + `rook-ceph-bucket`, `hdd-pool` + default `rook-ceph-hdd`, `ssd-pool` + `rook-ceph-ssd` | `toolbox` |
| traefik | chart 42.4.1 | Gateway API v1.7.0 CRDs | ✅ (kustomize inflates the chart) | ✅ | — | `postCertManager` (Helm route only) |
| certificateManager | v1.21.3 | Gateway API CRDs (from traefik) | ✅ (upstream manifest, patched) | ✅ | Cloudflare token Secret + `letsencrypt-dns01` ClusterIssuer | |
| postgresql | CloudNativePG v1.30.2 (chart 0.29.2) + Barman Cloud plugin v0.16.0 | — | ✅ (upstream manifests) | ✅ (plugin via kustomize) | `db` namespace + `cluster00` (3 instances on `rook-ceph-ssd`) + daily snapshot backup + WAL archive and weekly base backup to Backblaze B2 (key in git-ignored `postgresql/base/backblaze.env`) | `snapshot`, `b2backup`, `snapshots` (see `postgresql/README.md`) |
| harbor | chart 1.19.4 running Harbor v2.16.0 images | `harbor` namespace, password Secrets, `harbor` DatabaseRole + Database (cluster00) | — | ✅ (Helm only) | — | `password` (see `harbor/README.md`) |
| forgejo | chart 17.3.3 → Forgejo 15.0.12 (LTS); forgejo-runner 13.2.2 | `forgejo` namespace (PSA `privileged`), Secrets (incl. runner secrets), `forgejo` DatabaseRole + Database (cluster00) | — | ✅ (Helm only) | — | `runners`, `password` (see `forgejo/README.md`) |
| monitoring | kube-prometheus-stack chart 93.11.0 (Prometheus Operator v0.95.2, Grafana 13.3.2) | `monitoring` namespace (PSA `privileged`), Grafana admin Secret | — | ✅ (Helm only) | — | `password` (see `monitoring/README.md`) |
| cloudflared | cloudflared 2026.11.2 | Cloudflare tunnel + token (by hand), traefik `postCertManager` | — | — | Connector Deployment (2 replicas, one per worker) + token Secret from git-ignored `cloudflared/base/cloudflared.env` | `whoami` (see `cloudflared/README.md`) |
| brietzke-website | nginx-unprivileged 1.31.7 serving the Hugo site from the `brietzke-me/website` Forgejo repo | Image in Harbor (`library/brietzke-me`, built by Forgejo Actions), traefik `public` + cloudflared | — | — | `brietzke-me` namespace, Deployment (2 replicas), HTTPRoute `brietzke.me` on `traefik-public` | `deploy TAG=<sha12>` |
| brietzke-auth | Pocket ID v2.19.3 (distroless, pinned by digest) | traefik `public` + cloudflared, postgresql `cluster00` | — | — | `pocket-id` namespace, 1 replica, `pocketid` DatabaseRole + Database in cluster00; secrets in git-ignored `brietzke-auth/base/*.env` | `publish` / `unpublish` (see `brietzke-auth/README.md`) |
| brietzke-video | MiroTalk C2C 1.5.10 (`mirotalk/c2c` pinned by digest) | traefik `public` + cloudflared | — | — | `mirotalk` namespace, 1 replica, HTTPRoute `video.brietzke.me` on `traefik-public` login via Pocket ID OIDC (guests join existing rooms without an account); STUN only, no TURN; secrets and OIDC client in git-ignored `brietzke-video/base/mirotalk.env` | (see `brietzke-video/README.md`) |

## Cluster
Talos Linux v1.14, bootstrapped from `../talos_olympians`. Kubernetes v1.37.1, amd64, kernel 6.18.

| Node | IP (lan0) | Role | Disks |
|---|---|---|---|
| zeus | 192.168.3.9 | control plane (tainted), API endpoint | 500 GB NVMe: Talos |
| ares | 192.168.3.11 | worker | `sda` 512 GB Micron SSD: Talos · `sdb` 1 TB WD Green SSD: Ceph `ssd` · `sdc` 4 TB Seagate HDD: Ceph `hdd` |
| hades | 192.168.3.13 | worker | same as ares |
| hera | 192.168.3.17 | worker | same as ares |

- **Node labels.** Every node has `topology.kubernetes.io/region=HOME` and `topology.kubernetes.io/zone=olympians`. Talos sets them from `KubeNodeConfig.labels`, in `../talos_olympians/{worker,controlplane}.yaml`, with `labels-*.yaml` as the patches. The whole cluster is one zone, so zone-aware charts see a single failure domain; spreading across hosts still uses `kubernetes.io/hostname`. The workers' `node-role.kubernetes.io/worker` label is set with `make worker-roles`, not by Talos. On workers, Talos labels through the kubelet's credentials, and NodeRestriction forbids those from setting `node-role.kubernetes.io/*`. The update then fails as a whole and blocks the other labels too. Re-run `make worker-roles` after a worker is rebuilt.
- Pod CIDR `10.254.0.0/22`, service CIDR `172.16.0.0/23`. Talos ships no CNI and no kube-proxy; Cilium replaces both and reaches the API through KubePrism (`localhost:7445`).
- LoadBalancer IPs come from Cilium LB IPAM, `192.168.3.200–204`. The workers answer ARP for them on `ens4f0` (lan0). Traefik's Gateway is pinned to **`192.168.3.200`**, and Forgejo's SSH to **`192.168.3.201`**.
- Talos enforces Pod Security Admission, and only `kube-system` is exempt. Namespaces with privileged pods need `pod-security.kubernetes.io/enforce=privileged`. Rook's `rook-ceph` is labeled that way by both routes, and so is `forgejo` (its runners' dind sidecar).

## Storage

| Class | Kind | Backed by | Use for |
|---|---|---|---|
| `rook-ceph-hdd` (**default**) | StorageClass, dynamic | Ceph RBD, `hdd-pool`: 3 replicas across the workers' 4 TB Seagate HDDs, ~3.6 TiB usable | Bulk data (Harbor's image layers, anything without a class) |
| `rook-ceph-ssd` | StorageClass, dynamic | Ceph RBD, `ssd-pool`: 3 replicas across the workers' 1 TB WD Green SSDs, ~930 GiB usable | Databases and latency-sensitive volumes (`cluster00`, Forgejo's repositories) |
| `rook-ceph-snapclass` (**default**) | VolumeSnapshotClass, `deletionPolicy: Delete` | Ceph RBD snapshots (copy-on-write) | Snapshots of either class, CNPG backups |
| `rook-ceph-bucket` | StorageClass for ObjectBucketClaims | Ceph RGW object store `s3`: data in `s3.rgw.buckets.data` (HDD, 3 replicas, **500 GiB quota**), metadata pools on SSD | S3 buckets for apps. In-cluster endpoint `http://rook-ceph-rgw-s3.rook-ceph.svc:80` |

- Both classes use `reclaimPolicy: Delete`. Deleting a PVC deletes its data.
- **The HDDs are SMR** (Seagate ST4000DM004). Sequential and read-heavy use is fine. Sustained random writes, and Ceph backfill after a disk or node loss, are slow. Put databases on `rook-ceph-ssd`.
- OSDs are selected by WWN (`devicePathFilter: ^/dev/disk/by-id/wwn-0x(5001b448|5000c500)`: WD and Seagate), not by `sdX`, because kernel disk names can change between boots. The Micron system disk (`0x500a0751…`) never matches. Talos landed on the Micron even though `../talos_olympians/worker-disk.yaml` selects `/dev/sdb`. Ceph sets the `ssd` / `hdd` device class from each disk's rotational flag.
- With three hosts and `size: 3`, each pool keeps serving with one worker down (`min_size: 2`), but can't heal until it returns.
- **Object store `s3`** (`rook/base/ceph-object-store.yaml`):
  - One RGW gateway. Data is replicated ×3 on the HDDs. Erasure coding isn't used: the most three hosts allow is 2+1, which stops accepting writes while a worker is down.
  - **Capacity ceiling:** a pool quota of **500 GiB of stored data** on the data pool, about 1.5 TiB raw at size 3. At the quota, new writes fail and reads and deletes keep working. The block pools are unaffected. To change it, edit `dataPool.quotas.maxSize` and run `make -C rook olympians`.
  - **Getting a bucket:** create an `ObjectBucketClaim` with `storageClassName: rook-ceph-bucket`. It produces a Secret (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) and a ConfigMap (`BUCKET_HOST`, `BUCKET_PORT`, `BUCKET_NAME`), both named after the claim.
  - **Per-claim limits:** `additionalConfig.maxSize` / `maxObjects` are applied as a quota on the **claim's own user**, not on the bucket. Each claim gets its own user, so in practice they limit that bucket. Over the limit, uploads get `403 QuotaExceeded`.
  - Deleting a claim deletes its bucket and its data (`reclaimPolicy: Delete`).
  - `preservePoolsOnDelete: true` keeps the pools if the `CephObjectStore` itself is deleted.
  - **On the LAN, HTTPS only** (`rook/base/ceph-object-store-route.yaml`). It isn't reachable through the Cloudflare tunnel:
    - **path-style:** `https://s3.faultycloud.xyz/<bucket>/<key>`, using the existing `*.faultycloud.xyz` certificate.
    - **virtual-hosted-style:** `https://<bucket>.s3.faultycloud.xyz/<key>`, which AWS SDKs use by default. A wildcard certificate covers only one level of names, so this has its own listener (`websecure-s3`) and certificate (`s3-faultycloud-xyz-tls`) in `traefik/helm/postCertManager.yaml`.
    - **Bucket from the hostname:** `hosting.dnsNames: [s3.faultycloud.xyz]` tells RGW to read the bucket name from the hostname. RGW then rejects any `Host` it doesn't know, except the in-cluster Service name, which Rook adds automatically.
    - **Route attachment:** `make olympians` labels the `rook-ceph` namespace `olympians/traefik-gateway=allowed`.
    - **Bucket claims** still return the in-cluster endpoint, `rook-ceph-rgw-s3.rook-ceph.svc:80`.
  - **Tested 2026-11-25:**
    - Upload, list and read back through a claim.
    - A claim with `maxSize: 1M` accepted 300 KB and rejected 3 MB with `QuotaExceeded`.
    - Over `https://s3.faultycloud.xyz`: a path-style upload, a virtual-hosted read-back, and a 200 MB multipart upload in 5 s.
    - The certificate matches each name, and HTTP gets a 301 to HTTPS.

## Order
Running `make install` (kustomize) or `make helm` at the repo root installs everything in dependency order:

1. **cilium**: CNI, the LoadBalancer IP pool and L2 announcements. Without the pool and policy, every LoadBalancer Service, including traefik's, stays `<pending>` or unreachable.
2. **external-snapshotter**: snapshot CRDs and controller. It must come before rook and postgresql (see [Install-order dependencies](#install-order-dependencies)).
3. **rook**: the Ceph cluster on the SSD and HDD of each of the three workers. zeus has no data disk and gets no OSD.
4. **traefik**: Gateway API CRDs, Traefik and the `traefik-gateway` Gateway (HTTP only at this point) on `192.168.3.200`.
5. **certificateManager**: cert-manager and the `letsencrypt-dns01` DNS-01 issuer. Before running it, `cp certificateManager/base/cloudflare.env.example certificateManager/base/cloudflare.env` and fill in the Cloudflare API token. The file is git-ignored, and kustomize generates the Secret from it.
6. **postgresql**: the CloudNativePG operator and the Barman Cloud plugin. The plugin uses cert-manager for its TLS, so it comes after certificateManager.

The root targets stop there. Four more steps are manual, in this order:

- `make -C traefik postCertManager` switches the Gateway to HTTPS for `faultycloud.xyz`, using the `faultycloud-xyz-tls` certificate from `letsencrypt-dns01`. It needs the Helm route (`make -C traefik helm` or `make helm`) and certificateManager's `olympians` step.
- `make -C postgresql olympians` creates `cluster00`, its backup schedules and the Backblaze B2 ObjectStore (`s3://bbrietzke-backups/kube-olympians/postgresql/`). First `cp postgresql/base/backblaze.env.example postgresql/base/backblaze.env` and fill in the B2 key. The file is git-ignored, and the target refuses to run without it. It waits up to `PG_TIMEOUT` (default 15m) for the cluster to be Ready, then for WAL archiving to B2, and takes the first B2 base backup if none exists.
- `make -C harbor helm` installs Harbor at `https://harbor.faultycloud.xyz`, after `cluster00` and `traefik postCertManager`. It generates its own git-ignored passwords and creates a `harbor` DatabaseRole and Database for cluster00 without modifying cluster00 or the postgresql component (see `harbor/README.md`). The name must resolve to `192.168.3.200` on the LAN, including on the nodes, for pushes and pulls.
- `make -C forgejo helm runners` installs Forgejo at `https://git.faultycloud.xyz` (SSH on `192.168.3.201` as `git-ssh.faultycloud.xyz`, which needs its own DNS record) and its two Actions runners, after `cluster00` and `traefik postCertManager`. Like harbor, it generates its own git-ignored credentials and uses a DatabaseRole and a Database instead of modifying cluster00.
- `make -C monitoring helm` installs Prometheus, Alertmanager and Grafana, LAN-only at `https://{prometheus,alertmanager,grafana}.faultycloud.xyz`, with their data on `rook-ceph-ssd`. Prometheus discovers monitors and rules in every namespace. On Talos, the scheduler, controller-manager and etcd aren't scraped yet (see `monitoring/README.md`).
- `make -C cloudflared olympians` connects the Cloudflare tunnel for `brietzke.me` to the `traefik-public` Gateway, after `traefik postCertManager`. The tunnel and its routes are created by hand in Cloudflare first (see `cloudflared/README.md`).
- `make -C brietzke-website deploy TAG=<sha12>` serves `https://brietzke.me` (apex only, public only) from the image the `brietzke-me/website` repo's Forgejo build pushed to Harbor. It records the tag in `brietzke-website/overlays/olympians`, so commit it afterwards.
- `make -C brietzke-auth olympians publish` runs Pocket ID at `https://auth.brietzke.me`, the passkey-only OIDC login for `brietzke.me` apps. Its data is in a `pocketid` database in cluster00. Apps log users in themselves, so Traefik does no authentication. After the first `publish`, claim the admin at `/setup` immediately (see `brietzke-auth/README.md`).
- `make -C brietzke-video olympians` serves MiroTalk C2C video calls at `https://video.brietzke.me` (public, experimental). Creating a room needs a Pocket ID login; guests join existing rooms without one. The web app and signaling go through the tunnel, and media goes browser to browser with public STUN and no TURN (see `brietzke-video/README.md`). Needs brietzke-auth.

After `postCertManager`, `traefik-gateway` has five listeners: `web` and `websecure` for `faultycloud.xyz`, `web-wildcard` and `websecure-wildcard` for `*.faultycloud.xyz`, and `websecure-s3` for `*.s3.faultycloud.xyz` (the S3 store's bucket names, with its own certificate `s3-faultycloud-xyz-tls`). A wildcard listener doesn't match the bare domain, hence the pairs. Both HTTPS listeners share the `faultycloud-xyz-tls` certificate, which covers both names. An HTTPRoute can attach only from a namespace labeled `olympians/traefik-gateway=allowed`:

```sh
kubectl label namespace <ns> olympians/traefik-gateway=allowed
```

```yaml
# HTTPRoute in that namespace
spec:
  parentRefs: [{name: traefik-gateway, namespace: traefik}]
  hostnames: ["app.faultycloud.xyz"]
```

A route from an unlabeled namespace, including `traefik` itself, is rejected with `Accepted=False (NotAllowedByListeners)`. Every plain-HTTP request is redirected to HTTPS with a `301`, keeping the host, path and query. Traefik does this on the `web` entrypoint before any route matches, so apps never serve over HTTP and their HTTPRoutes need no redirect filter. These settings are only in `traefik/helm/postCertManager.yaml`. The pre-certificate `helm/install.yaml` route still has a single apex HTTP listener.

`postCertManager` also applies a second Gateway, **`traefik-public`**, for `brietzke.me` and `*.brietzke.me`. It is reachable only through the Cloudflare tunnel, on Traefik's `public` entrypoint (port 8100). That entrypoint is served by the ClusterIP Service `traefik-internal` and is not on `192.168.3.200`. Routes attach to it only from namespaces labeled `olympians/exposure=public`. See `cloudflared/README.md`.

Every `prerequisites`, `install` and `helm` target blocks until what it created is ready, so targets can be chained (`make -C rook install olympians`). Ready means CRDs are Established and all Deployments, DaemonSets and StatefulSets have rolled out (see `hack/wait-ready.sh`). Some components add their own check:

- **cilium**: `helm` waits for the `cilium` DaemonSet and `cilium-operator`. `olympians` waits until the API server accepts the pool and policy.
- **rook**: waits for the CephCluster to reach `Ready` (up to `CEPH_TIMEOUT`, default 30m) and for the RBD CSI driver to be registered. `olympians` waits for `hdd-pool` and `ssd-pool` to be Ready.
- **traefik**: waits for the Gateway to be `Programmed`.
- **certificateManager**: waits until its webhook accepts the issuer config. `olympians` waits for the ClusterIssuer to be Ready (registered with Let's Encrypt).
- **postgresql**: `install` / `helm` also wait for the Barman Cloud plugin. `olympians` waits until the webhook accepts `cluster00`, for the cluster to be Ready, and until every instance has the barman-cloud sidecar and `ContinuousArchiving` is `True`. `snapshot` and `b2backup` wait for the Backup to complete, up to `SNAPSHOT_WAIT` seconds (default 600).
- **harbor**: `prerequisites` waits until the `harbor` DatabaseRole is applied with no error, then for the `harbor` Database. `helm` waits for every workload and for the HTTPRoute to be Accepted.
- **forgejo**: `prerequisites` waits for the `forgejo` DatabaseRole (applied, no error) and Database. `helm` waits for the workload, for the HTTPRoute to be Accepted and for the SSH LoadBalancer IP `192.168.3.201`. `runners` checks that each registration returns the expected UUID, then waits for the StatefulSet.

Other timeouts default to `WAIT_TIMEOUT=300s`; override with, for example, `make install WAIT_TIMEOUT=10m`.

## Install-order dependencies
Some controllers only detect CRDs when they start. If the CRDs are installed after the controller, it keeps running without them until it is restarted:

| Installed late | Affected | Symptom | Fix |
|---|---|---|---|
| external-snapshotter (snapshot CRDs) | rook's RBD and CephFS CSI controllers | `csi-snapshotter` sidecar logs `failed to list *v1.VolumeSnapshotContent` | `kubectl -n rook-ceph rollout restart deploy/rook-ceph.rbd.csi.ceph.com-ctrlplugin deploy/rook-ceph.cephfs.csi.ceph.com-ctrlplugin` |
| external-snapshotter (snapshot CRDs) | CloudNativePG operator | `method: volumeSnapshot` rejected: "missing VolumeSnapshot CRD" | `kubectl -n cnpg-system rollout restart deploy/cnpg-controller-manager` |
| certificateManager `olympians` (ClusterIssuer) | traefik `postCertManager` | Certificate stuck `Ready: False`, "ClusterIssuer not found" | Run certificateManager `olympians`. cert-manager retries on its own. |

The root `make install` / `make helm` order avoids all three.

## Local patches to upstream
These are deliberate deviations from the pinned upstream manifests. Keep them when bumping versions, and drop any that upstream fixes:

- **cilium** (`helm/values.yaml`): Talos settings (`cgroup.autoMount` off, explicit agent capabilities, KubePrism on `localhost:7445`), `kubeProxyReplacement`, `l2announcements` and `k8sClientRateLimit` 50/100.
- **rook** (`overlays/install`, mirrored in `helm/cluster.yaml`):
  - `csi.cephfs: {}`. Upstream `cluster.yaml` v1.21.2 leaves it with only commented-out keys, which parses as `null` and fails CRD validation.
  - `devicePathFilter` by WWN with `useAllDevices: false`.
  - **Not** patched: the cephx `keyType: aes` stays, because the nodes run kernel 6.18. Upstream's `allowedCiphers: [aes256k]` needs Linux 7.0+ on every node.
- **rook** (`overlays/prerequisites`, and the `helm` target): Pod Security `privileged` labels on the `rook-ceph` namespace.
- **rook** (`helm/operator.yaml`, `helm/cluster.yaml`): Prometheus monitoring is on, with Ceph's alert rules. `CephHealthWarning` is overridden to ignore the permanent `AUTH_INSECURE_*` warnings (see `monitoring/README.md`). That needs the Prometheus Operator CRDs from `monitoring`, which is a chicken-and-egg problem on a rebuild from scratch, also explained there.
- **rook** (`helm/csi-drivers.yaml` + `helm/operator.yaml`, Helm route only): chart v1.21.2 installs the ceph-csi-operator but none of the objects its drivers need. `csi-drivers.yaml` adds the `OperatorConfig` and RBD/CephFS `Driver` objects (from upstream `operator.yaml`) and the `ceph-csi-{rbd,cephfs}-{ctrl,node}plugin` ServiceAccounts and RBAC (from upstream `csi-operator.yaml`). `operator.yaml` sets `CSI_SERVICE_ACCOUNT_PREFIX=ceph-csi-` to match; the chart's default `""` makes the driver pods ask for `rbd-ctrlplugin-sa`, which doesn't exist. Without these, `make helm` times out on the CSI driver. Re-copy them when bumping the chart.
- **certificateManager** (`overlays/install`): `--enable-gateway-api` and `--enable-certificate-owner-ref=true`, to match `helm/values.yaml`.
- **traefik** (`helm/*.yaml`): `lbipam.cilium.io/ips: 192.168.3.200` on the Service. `postCertManager.yaml` also adds the `public` entrypoint (8100, `expose.internal` only, forwarded headers trusted from `10.254.0.0/22`) and the `traefik-internal` ClusterIP Service.
- **postgresql**:
  - `shared_buffers: 256MB`. It must fit well inside the 2Gi memory limit.
  - Cold (`online: false`) volume-snapshot backups. They were chosen when there was no WAL archive, and they stay self-contained, so a snapshot restore never needs B2. With B2 archiving in place they could switch to hot (`online: true`), which avoids fencing a standby.
  - Barman Cloud sidecar env `AWS_REQUEST_CHECKSUM_CALCULATION` / `AWS_RESPONSE_CHECKSUM_VALIDATION` = `when_required`, the plugin's workaround for S3-compatible stores (B2).
  - The B2 ScheduledBackup has `immediate: false`. `make olympians` takes the first base backup once the sidecars are up.
- **forgejo**:
  - The runner StatefulSet is adapted from upstream `examples/kubernetes/dind-docker.yaml`, with images updated to runner 13.2.2 and `docker:28-dind` (the example pins 6.4.0 / 28.3.0), and offline pre-shared-secret registration instead of the token init container.
  - Repositories on `rook-ceph-ssd`; SSH pinned to `192.168.3.201` with `lbipam.cilium.io/ips`.
- **harbor**:
  - All images overridden to `v2.16.0` on chart 1.19.4 (built for 2.15.4). Switch to the first 2.16 chart and drop the overrides.
  - `maxOpenConns: 30` / `maxIdleConns: 5`, down from 900/100, so Harbor can't exhaust cluster00's 100 connections.

## Uninstalling
`make uninstall` or `make uninstall-helm` tears everything down in reverse. They remove Cilium's IP pool and L2 policy, but **never Cilium itself**: without a CNI every node goes NotReady. Remove it on purpose with `make -C cilium uninstall-helm`. Uninstalling removes CRDs, which deletes every object of those kinds. Some components lose data when uninstalled:

- **forgejo**: `uninstall-helm` removes the runners and the release. The repository PVC, the `forgejo` namespace and Secrets, and the `forgejo` database and role in cluster00 are kept.
- **harbor**: `uninstall-helm` removes the release only. The PVCs (image layers), the `harbor` namespace and its Secrets, and the `harbor` database and role in cluster00 are kept. The root `uninstall` targets remove Harbor before postgresql.
- **postgresql**: deletes `cluster00`, its volumes (`rook-ceph-ssd` is `Delete`) and the `db` namespace. That includes **every Backup and VolumeSnapshot**, so the snapshot backups go too. The Backblaze B2 bucket is not touched, so the off-cluster backups survive. With no cluster archiving there any more, nothing prunes them.
- **external-snapshotter**: deletes every VolumeSnapshot in the cluster.
- **traefik**: both uninstall targets remove the Gateway API CRDs, which deletes every Gateway and HTTPRoute in the cluster. certificateManager also depends on those CRDs.
- **rook**: Rook does not wipe the OSD drives, and `/var/lib/rook` stays on each node. Re-using a drive needs a manual wipe. `talosctl wipe disk` (fast) is **not enough**: since Squid, BlueStore keeps copies of its label at 0, 1, 10, 100 and 1000 GiB, and Rook skips the disk as "belonging to a different ceph cluster". Zero 1 MiB at each of those offsets, or use `--method zeroes` (hours on the 4 TB drives).

Requires `kubectl` (1.37), `kustomize` (5.x), `helm` (4.x) and, for node work, `talosctl`.
