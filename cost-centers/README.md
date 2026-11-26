# Cost centers: chargeback labels

Every namespace carries a **`cost-center`** label, and the Grafana dashboard **OpenCost / Cost centers (olympians)** groups cost by it (see `opencost/README.md`).

| Cost center | Namespaces |
| --- | --- |
| `brietzke` | `brietzke-me` (site), `mirotalk` (video), `pocket-id` (auth) |
| `platform` | everything else: Kubernetes and Talos system namespaces, Cilium, Rook/Ceph, Traefik, cert-manager, CloudNativePG and `db`, cloudflared and `whoami`, Forgejo, Harbor, monitoring, OpenCost |

| Task | Command (from `cost-centers/`) |
| --- | --- |
| Apply the labels and the warn-only policy | `make olympians` (or `make labels` / `make policy`) |
| Show every namespace's cost center; fail if any is missing | `make check` |

## Where the label lives
- **Namespaces this repo creates** carry it in their own manifest (for example `brietzke-auth/base/namespace.yaml`), so it's set the moment the namespace is created.
- **Namespaces nothing in the repo creates** are listed in `base/namespaces.yaml`: Kubernetes' own, Cilium's, upstream installers' (`cert-manager`, `cnpg-system`) and the Helm-route `rook-ceph` and `traefik`. These are **partial** objects, applied server-side with field manager `cost-centers`. This component owns only the `cost-center` label, so it never fights Helm, Talos or the owning component, and they never remove it.

## More specific labels
The label can also go on a **pod** (pod template labels) or a **PVC**, and the more specific one wins:

| Cost | Charged to |
| --- | --- |
| Compute (CPU and memory requests) | the pod's `cost-center`, else its namespace's, else `unallocated` |
| Storage (PV size × price) | the PVC's `cost-center`, else the claim namespace's, else `unallocated` |

- **Pod labels** reach Prometheus through OpenCost (`kube_pod_labels`). **PVC labels** come from kube-state-metrics, whose allowlist in `monitoring/helm/values.yaml` permits only `cost-center` on PVCs.
- **Idle capacity** (node cost minus allocated compute) is shown on its own line and isn't shared out to cost centers.
- **`unallocated`** should stay at $0. If it doesn't, something is unlabeled: run `make check`.

## Allowed values and the warn-only policy
`policy/` installs a **ValidatingAdmissionPolicy**, `cost-center-label`, that checks every Namespace create and update:

| Namespace | Result |
| --- | --- |
| no `cost-center` label | warning: `namespace X has no cost-center label ... add cost-center: <one of brietzke, platform>` |
| a value that isn't allowed, e.g. `platfrom` | warning: `namespace X has cost-center=platfrom, which is not in ConfigMap kube-system/allowed-cost-centers ...` |
| an allowed value | nothing |

- **It never blocks anything.** The binding's actions are `Warn` and `Audit` only, deliberately with no `Deny`, and `failurePolicy: Ignore` lets requests through if the policy itself errors. Warnings show in `kubectl` and Helm output; `Audit` also records them in the API server's audit log.
- **Allowed values** are the keys of ConfigMap `kube-system/allowed-cost-centers` (`policy/allowed-cost-centers.yaml`); each key's text is just a note. The policy reads the ConfigMap live.
- **Only namespaces are checked.** Pod and PVC labels aren't, and running workloads are never affected.
- **Expect a warning from Helm's `--create-namespace`** (the Helm routes for traefik and cert-manager), which creates the namespace unlabeled. Then run `make labels` here to label it.
- Turn it off with `kubectl delete validatingadmissionpolicybinding cost-center-label`.

## Adding a cost center
1. Add the value as a key in `policy/allowed-cost-centers.yaml`, for example `eng-web: "what it's for"`, and run `make policy`.
2. Label with it, for example `cost-center: eng-web`. For a new namespace, put the label in its manifest. For a namespace created outside the repo, add it to `base/namespaces.yaml` and run `make labels`.

The dashboard picks up new values automatically, with no change needed.
