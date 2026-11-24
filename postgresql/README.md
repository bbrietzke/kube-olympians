# PostgreSQL — Backups

`cluster00` (namespace `db`) is a three-instance CloudNativePG cluster on the `rook-ceph-ssd` StorageClass. It has two independent kinds of backup:

| | Volume snapshots | Backblaze B2 (Barman Cloud plugin) |
| --- | --- | --- |
| What | CSI snapshot of one instance's 64Gi data volume (`rook-ceph-snapclass`) | Continuous WAL archive plus base backups in `s3://bbrietzke-backups/kube-olympians/postgresql/cluster00/` |
| Schedule | Daily 03:00 UTC (`cluster00-daily`) | WAL continuously (within minutes); base backup Sundays 04:00 UTC (`cluster00-b2-weekly`) |
| Restores to | The moment of a snapshot | **Any point in time** within the last 30 days |
| Survives | Mistakes and bad writes | Also the loss of Ceph or of the whole cluster |
| Retention | None automatic (delete Backups by hand) | 30 days, enforced by the plugin |
| Restore speed | Fast (local copy-on-write clone) | Downloads from B2 (~80 s for today's small database) |

| Task | Command (from `postgresql/`) |
| --- | --- |
| Take a snapshot now | `make snapshot` |
| Take a B2 base backup now | `make b2backup` |
| Tag either one | `make snapshot SNAPSHOT_LABEL=pre-upgrade`, `make b2backup SNAPSHOT_LABEL=pre-upgrade` |
| List backups, snapshots and WAL archiving status | `make snapshots` |
| Delete one snapshot backup and its snapshot | `kubectl -n db delete backup <name>` |
| Pause a schedule | `kubectl -n db patch scheduledbackup <cluster00-daily\|cluster00-b2-weekly> --type merge -p '{"spec":{"suspend":true}}'` |
| Restore | See [Restoring](#restoring) (snapshots) or [Restoring from B2](#restoring-from-b2-point-in-time) |

## How a snapshot backup works

Every backup is **cold**: CNPG fences one standby (stops Postgres on it), snapshots that instance's PVC, then unfences it. A cold snapshot is consistent by itself, so it needs no WAL archive. This is the approach CNPG recommends when there is no archive.

- The **primary keeps serving** throughout. Backups target `prefer-standby` and only fall back to the primary if no standby is healthy. A backup on the primary makes the cluster read-only for its duration.
- A backup takes about **30 seconds**. The fenced standby catches up and is Ready again about 30 seconds later, so `kubectl -n db get cluster` briefly shows `READY 2` of 3.
- Ceph snapshots are copy-on-write. A new snapshot costs almost nothing, and grows only as the data on the volume changes.

The settings live in `overlays/olympians/kustomization.yaml` as a patch on the Cluster:

```yaml
spec:
  backup:
    target: prefer-standby
    volumeSnapshot:
      className: rook-ceph-snapclass
      online: false                 # cold
      snapshotOwnerReference: backup
```

`snapshotOwnerReference: backup` ties each VolumeSnapshot to its CNPG `Backup` object. **Deleting the Backup deletes the snapshot**, and the class's `deletionPolicy: Delete` then removes the Ceph snapshot as well. Backups themselves have no owner, so they survive deleting the `cluster00` Cluster.

## Scheduled backups

`overlays/olympians/backup.yaml` defines the ScheduledBackup `cluster00-daily`. It runs at **03:00 UTC every day** and is named `cluster00-daily-<timestamp>`. CNPG cron has six fields with seconds first: `"0 0 3 * * *"`. It is applied with the rest of the cluster by `make olympians`, and it took a first backup immediately.

## Ad-hoc snapshots

Take one before anything risky, such as a schema migration, an upgrade or a bulk delete:

```sh
make snapshot SNAPSHOT_LABEL=pre-upgrade
```

This builds `overlays/snapshot`, a single CNPG `Backup` with `method: volumeSnapshot`, and creates it as `cluster00-<SNAPSHOT_LABEL>-<UTC timestamp>`. It then waits until CNPG reports the backup `completed`, exiting 0, or `failed`, exiting 1. `SNAPSHOT_LABEL` defaults to `adhoc`. The wait limit is `SNAPSHOT_WAIT`, default 600 seconds.

Kustomize cannot build an object without a fixed name, so the overlay uses a placeholder name, `cluster00-snapshot-placeholder`, which the Makefile replaces on every run. Do not `kubectl apply` the overlay by hand: you would create the placeholder-named backup once, and re-applying it does nothing.

The same thing without make:

```sh
kubectl create -f - <<EOF
apiVersion: postgresql.cnpg.io/v1
kind: Backup
metadata:
  name: cluster00-manual-$(date -u +%Y%m%d%H%M%S)
  namespace: db
  labels: {cnpg.io/cluster: cluster00}
spec:
  cluster: {name: cluster00}
  method: volumeSnapshot
EOF
```

Ad-hoc backups carry the label `olympians/backup-type=adhoc`, so they can be listed separately with `kubectl -n db get backup -l olympians/backup-type=adhoc`.

## Retention

**Nothing deletes old backups automatically.** CNPG's `retentionPolicy` only applies to object-store backups. Prune by deleting old `Backup` objects, which removes each one's snapshot as well:

```sh
make snapshots                                      # oldest first
kubectl -n db delete backup cluster00-daily-20261121231754
```

## Restoring

A snapshot restores into a **new** Cluster that bootstraps from it. Restoring always lands exactly at the moment of a backup. Point-in-time recovery between backups needs a WAL archive, which this setup does not have.

### Side by side (recommended first step)

This leaves `cluster00` untouched, so you can inspect the data or copy pieces back:

```sh
kubectl apply -f - <<'EOF'
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: cluster00-restore
  namespace: db
spec:
  instances: 1
  storage: {size: 64Gi, storageClass: rook-ceph-ssd}    # at least the snapshot's RESTORESIZE
  bootstrap:
    recovery:
      volumeSnapshots:
        storage:
          name: cluster00-daily-20261121231754      # the VolumeSnapshot name (same as the Backup)
          kind: VolumeSnapshot
          apiGroup: snapshot.storage.k8s.io
EOF
kubectl -n db wait cluster/cluster00-restore --for=condition=Ready --timeout=15m
kubectl -n db exec -it cluster00-restore-1 -c postgres -- psql -U postgres -d app
```

Delete it with `kubectl -n db delete cluster cluster00-restore` when you're done. The source snapshot is not affected. This procedure has been tested: a row written just before a backup was present in the restored cluster.

### Replacing cluster00

To roll `cluster00` itself back to a snapshot:

1. Take a snapshot of the current state first (`make snapshot SNAPSHOT_LABEL=before-restore`), in case you need it.
2. Stop the apps that write to it.
3. `kubectl -n db delete cluster cluster00`. This deletes its pods, PVCs, data and Secrets. The Backups, their VolumeSnapshots and the `cluster00-daily` ScheduledBackup stay.
4. Temporarily add the `bootstrap` block to `base/cluster00.yaml`, directly under `instances: 3`, then run `make olympians`:
   ```yaml
     bootstrap:
       recovery:
         volumeSnapshots:
           storage:
             name: <VolumeSnapshot name from `make snapshots`>
             kind: VolumeSnapshot
             apiGroup: snapshot.storage.k8s.io
   ```
5. Once it is Ready, remove the `bootstrap` block from `base/cluster00.yaml` and run `make olympians` again. The API server accepts the change without restarting anything. CNPG fills in an `initdb` default in the live spec, but that field is only read when a cluster is created.
6. Restart the apps. **The `app` password changes**: CNPG generates a new `cluster00-app` Secret and resets the role's password to match it, so apps must pick up the new Secret.

This procedure was tested on 2026-11-21 with marker rows on either side of a snapshot. The restored cluster had the row written before the snapshot and not the one written after. It took about 2 minutes to reach `3/3` Ready, with both replicas streaming and the restored data on each.

`make uninstall` is **not** a restore path. It deletes the `db` namespace, and with it every Backup and VolumeSnapshot. It does not touch the B2 bucket.

## Backblaze B2 backups

The [Barman Cloud plugin](https://github.com/cloudnative-pg/plugin-barman-cloud) v0.16.0 (`overlays/plugin-barman-cloud`, installed into `cnpg-system` by `make install`) adds a `plugin-barman-cloud` sidecar to every instance. It does two things:

- **Continuous WAL archiving.** Each completed WAL segment (16 MB, or less on a forced switch) is gzip-compressed and uploaded to B2. The Cluster's `ContinuousArchiving` condition shows whether this works. `make snapshots` prints it.
- **Base backups**, from a standby when one is healthy. Weekly by schedule, or on demand with `make b2backup`.

A restore takes the newest base backup from before the target time and replays archived WAL up to that time. That is why both are needed.

### Configuration

| What | Where |
| --- | --- |
| Bucket, path, endpoint, compression, retention, B2 checksum workaround | `base/object-store.yaml` (ObjectStore `backblaze`) |
| B2 key | `base/backblaze.env` (git-ignored) → Secret `backblaze-b2`. Template: `base/backblaze.env.example`. |
| Enable archiving on `cluster00` | `plugins` patch in `overlays/olympians/kustomization.yaml` (`serverName: cluster00`) |
| Weekly base backup | `overlays/olympians/backup-b2.yaml` |
| Ad-hoc base backup | `overlays/b2backup/`, used by `make b2backup` |

- **The key.** Use a B2 application key restricted to the bucket, with read and write access. `make olympians` refuses to run while `backblaze.env` is missing or still contains `REPLACE_ME`. To rotate the key, edit `backblaze.env` and re-run `make olympians`.
- **The bucket.** It needs the B2 lifecycle rule **"Keep only the last version of the file"**. Without it, B2 only *hides* the files that retention deletes and keeps billing for them.
- **The first base backup.** `make olympians` waits until every instance has the sidecar and archiving works, then takes a base backup if none exists yet. The schedule's own `immediate` run is off: it would start before the sidecars exist and fail with "requested plugin is not available".
- **Checksums.** `AWS_REQUEST_CHECKSUM_CALCULATION` and `AWS_RESPONSE_CHECKSUM_VALIDATION` are set to `when_required` on the sidecar, the plugin's documented workaround for S3-compatible stores that reject newer boto3 checksum headers. It is unverified whether B2 still needs it, and it is harmless if it doesn't.

### Checking it

```sh
make snapshots                                                   # backups + "WAL archiving to B2: True"
kubectl -n db get objectstore backblaze -o jsonpath='{.status.serverRecoveryWindow}'   # earliest restorable point
kubectl -n db exec cluster00-1 -c postgres -- psql -U postgres -qtAc \
  "SELECT last_archived_wal, last_archived_time, failed_count, last_failed_wal FROM pg_stat_archiver;"
```

`failed_count` counts failures since the instance started. A few right after a restart, before the sidecar was up, are normal as long as `last_archived_wal` keeps advancing.

### Restoring from B2 (point in time)

Restore into a **new** cluster. This example is side by side, which is the safe first step:

```sh
kubectl apply -f - <<'EOF'
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: cluster00-pitr
  namespace: db
spec:
  instances: 1
  storage: {size: 64Gi, storageClass: rook-ceph-ssd}
  bootstrap:
    recovery:
      source: b2
      recoveryTarget:
        targetTime: "2026-11-22T01:48:18Z"     # omit recoveryTarget to replay to the end of the archive
  externalClusters:
    - name: b2
      plugin:
        name: barman-cloud.cloudnative-pg.io
        parameters:
          barmanObjectName: backblaze
          serverName: cluster00                # the archive to read from
EOF
kubectl -n db wait cluster/cluster00-pitr --for=condition=Ready --timeout=15m
```

The restored cluster has **no `plugins` block**, so it reads the archive but never writes to it. To replace `cluster00` from B2, use the same steps as [Replacing cluster00](#replacing-cluster00), with this `bootstrap` and `externalClusters` instead of the snapshot one. Then:

- **Archive under a new `serverName`.** When the restored cluster is given the `plugins` block again, set its `serverName` to something new, for example `cluster00-r1`. Barman refuses to archive into a folder that already holds another timeline's WAL, and the old folder is what you'd fall back to. Restores from then on read from the new folder.
- **The `app` password changes**, as with snapshot restores.

This was tested on 2026-11-21. Marker rows were written 3 seconds before and after a target time. The cluster restored from B2 contained only the earlier row, reached Ready in 79 seconds, and needed nothing from the original cluster's volumes.

## Limits and gotchas

- **Snapshots share Ceph's failure domain.** The volume snapshots live in the same Ceph cluster as the database. B2 is the copy that survives losing Ceph or the cluster.
- **Snapshots have no point-in-time recovery.** Use B2 to restore between snapshots.
- **B2 retention needs an archiving cluster.** The plugin enforces the 30 days from a running cluster's sidecar. If `cluster00` is deleted for good, nothing prunes the bucket.
- **Network.** Large API responses between a workstation and the API server (seen on demigods) sometimes time out ("read: operation timed out"). Server-side applies are safe to re-run.
- **Install order.** The CNPG operator must start after the snapshot CRDs exist (install `external-snapshotter` first). If it started first, `method: volumeSnapshot` is rejected with "missing VolumeSnapshot CRD" until you run `kubectl -n cnpg-system rollout restart deploy/cnpg-controller-manager`.
- **A cold backup is rejected while any instance is already fenced.**
- If a backup sits in `started`, check `kubectl -n db describe backup <name>` and the snapshot-controller logs (`kubectl -n kube-system logs deploy/snapshot-controller`). CNPG gives up on a snapshot after 10 minutes by default.
