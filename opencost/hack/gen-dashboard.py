#!/usr/bin/env python3
"""Generate the OpenCost Grafana dashboards as ConfigMaps (picked up by the kube-prometheus-stack
Grafana sidecar, label grafana_dashboard=1, any namespace):

  base/grafana-dashboard.yaml               OpenCost / Cluster cost (olympians)
  base/grafana-dashboard-cost-centers.yaml  OpenCost / Cost centers (olympians)

Built only from OpenCost's exported metrics plus kube-state-metrics. Re-run after editing:
  python3 opencost/hack/gen-dashboard.py && make -C opencost prerequisites

Notes on the queries:
- OpenCost's series are deduplicated with max by (...): after an OpenCost restart the old pod's
  series linger for Prometheus's 5m lookback, which would otherwise double every cost.
- "Allocated" compute is CPU/RAM requests (OpenCost's container_*_allocation) priced per node;
  "idle" is node cost minus allocated compute. Storage is priced on each PV's size (pv_hourly_cost is
  per GiB-hour) and mapped to its claim via kube_persistentvolume_claim_ref.
- Cost centers (label cost-center): a pod's own label wins, else its namespace's, else
  "unallocated"; for storage, the PVC's own label (kube-state-metrics allowlist, monitoring/), else
  the claim namespace's, else "unallocated". Idle capacity is shown as its own line, not shared out.
- Prices are cloud-equivalent (see opencost/helm/values.yaml).
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
HOURS_PER_MONTH = 730
DS = {"type": "prometheus", "uid": "prometheus"}
GIB = 1073741824

# --- building blocks -------------------------------------------------------------------------------
NODE_TOTAL = "sum(max by (node) (node_total_hourly_cost))"

# Allocated compute cost per container, priced on its node (hourly).
CONTAINER_COST = (
    "max by (namespace, pod, container, node) (container_cpu_allocation)"
    " * on (node) group_left () max by (node) (node_cpu_hourly_cost)"
    f" + max by (namespace, pod, container, node) (container_memory_allocation_bytes) / {GIB}"
    " * on (node) group_left () max by (node) (node_ram_hourly_cost)"
)
ALLOC_NS = f"sum by (namespace) ({CONTAINER_COST})"
ALLOC = f"sum({CONTAINER_COST})"
POD_COST = f"sum by (namespace, pod) ({CONTAINER_COST})"

# Storage cost per PV (hourly), then per claim (namespace + persistentvolumeclaim).
PV_COST = (
    "max by (persistentvolume) (pv_hourly_cost)"
    f" * on (persistentvolume) group_left () max by (persistentvolume) (kube_persistentvolume_capacity_bytes) / {GIB}"
)
STORAGE = f"sum({PV_COST})"
PV_CLAIM = (
    'label_replace(label_replace('
    "max by (persistentvolume, claim_namespace, name) (kube_persistentvolume_claim_ref),"
    ' "namespace", "$1", "claim_namespace", "(.*)"),'
    ' "persistentvolumeclaim", "$1", "name", "(.*)")'
)
PVC_COST = (
    f"sum by (namespace, persistentvolumeclaim) ({PV_COST}"
    f" * on (persistentvolume) group_left (namespace, persistentvolumeclaim) {PV_CLAIM})"
)
STORAGE_NS = f"sum by (namespace) ({PVC_COST})"

# Cost-center labels.
NS_CC = 'max by (namespace, label_cost_center) (kube_namespace_labels{label_cost_center!=""})'
POD_CC = 'max by (namespace, pod, label_cost_center) (kube_pod_labels{label_cost_center!=""})'
PVC_CC = ('max by (namespace, persistentvolumeclaim, label_cost_center)'
          ' (kube_persistentvolumeclaim_labels{label_cost_center!=""})')


def attribute(cost, own_cc, key):
    """Series of `cost` (labels: namespace + key) carrying label_cost_center: own label, else the
    namespace's, else "unallocated"."""
    no_own = f"(({cost}) unless on (namespace, {key}) {own_cc})"
    return (
        f"(({cost}) * on (namespace, {key}) group_left (label_cost_center) {own_cc})"
        f" or ({no_own} * on (namespace) group_left (label_cost_center) {NS_CC})"
        f' or label_replace({no_own} unless on (namespace) {NS_CC}, "label_cost_center", "unallocated", "", "")'
    )


COMPUTE_ATTR = attribute(POD_COST, POD_CC, "pod")
STORAGE_ATTR = attribute(PVC_COST, PVC_CC, "persistentvolumeclaim")
COMPUTE_CC = f"sum by (label_cost_center) ({COMPUTE_ATTR})"
STORAGE_CC = f"sum by (label_cost_center) ({STORAGE_ATTR})"
# Compute and storage series have different label sets (pod vs persistentvolumeclaim), so `or` keeps
# both and the sum adds them per cost center.
TOTAL_CC = f"sum by (label_cost_center) (({COMPUTE_ATTR}) or ({STORAGE_ATTR}))"
# Keep only the "unallocated" series (empty, shown as $0, when everything is labeled).
UNALLOCATED = (f"sum(({TOTAL_CC}) and on (label_cost_center)"
               ' label_replace(vector(1), "label_cost_center", "unallocated", "", ""))')
COMPUTE_CC_NS = f"sum by (label_cost_center, namespace) ({COMPUTE_ATTR})"
STORAGE_CC_NS = f"sum by (label_cost_center, namespace) ({STORAGE_ATTR})"

NODE_CPU = f'max by (node) (node_cpu_hourly_cost) * on (node) max by (node) (kube_node_status_capacity{{resource="cpu"}})'
NODE_RAM = f'max by (node) (node_ram_hourly_cost) * on (node) max by (node) (kube_node_status_capacity{{resource="memory"}}) / {GIB}'


# --- panel helpers -----------------------------------------------------------------------------------
def monthly(expr):
    return f"({expr}) * {HOURS_PER_MONTH}"


def target(expr, legend="", ref="A", instant=False, fmt="time_series"):
    t = {"datasource": DS, "expr": expr, "legendFormat": legend, "refId": ref, "format": fmt}
    if instant:
        t.update({"instant": True, "range": False})
    return t


def stat(pid, title, expr, x, y, desc, w=6, color="blue"):
    return {
        "id": pid, "type": "stat", "title": title, "description": desc, "datasource": DS,
        "gridPos": {"h": 5, "w": w, "x": x, "y": y},
        "targets": [target(expr, instant=True)],
        "fieldConfig": {"defaults": {"unit": "currencyUSD", "decimals": 0, "noValue": "$0",
                                     "color": {"mode": "fixed", "fixedColor": color}}, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "value", "graphMode": "none",
                    "textMode": "value"},
    }


def bars(pid, title, expr, legend, x, y, w, desc, h=10):
    return {
        "id": pid, "type": "bargauge", "title": title, "description": desc, "datasource": DS,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "targets": [target(f"sort_desc({expr})", legend, instant=True)],
        "fieldConfig": {"defaults": {"unit": "currencyUSD", "decimals": 2, "min": 0,
                                     "color": {"mode": "continuous-BlYlRd"}}, "overrides": []},
        "options": {"orientation": "horizontal", "displayMode": "gradient", "showUnfilled": True,
                    "reduceOptions": {"calcs": ["lastNotNull"]}, "valueMode": "color"},
    }


def stacked(pid, title, expr, legend, y, desc):
    return {
        "id": pid, "type": "timeseries", "title": title, "datasource": DS, "description": desc,
        "gridPos": {"h": 9, "w": 24, "x": 0, "y": y},
        "targets": [target(expr, legend)],
        "fieldConfig": {"defaults": {"unit": "currencyUSD", "decimals": 3,
                                     "custom": {"stacking": {"mode": "normal"}, "fillOpacity": 30}},
                        "overrides": []},
        "options": {"legend": {"displayMode": "table", "placement": "right", "calcs": ["lastNotNull", "mean"]},
                    "tooltip": {"mode": "multi", "sort": "desc"}},
    }


def table(pid, title, targets, rename, y, desc, sort_by, h=8):
    return {
        "id": pid, "type": "table", "title": title, "datasource": DS, "description": desc,
        "gridPos": {"h": h, "w": 24, "x": 0, "y": y},
        "targets": targets,
        "transformations": [
            {"id": "merge", "options": {}},
            {"id": "organize", "options": {"excludeByName": {"Time": True}, "renameByName": rename}},
        ],
        "fieldConfig": {"defaults": {"unit": "currencyUSD", "decimals": 2}, "overrides": []},
        "options": {"showHeader": True, "sortBy": [{"displayName": sort_by, "desc": True}]},
    }


def dashboard(uid, title, description, panels):
    return {
        "uid": uid, "title": title, "description": description, "tags": ["opencost", "cost"],
        "timezone": "browser", "schemaVersion": 39, "version": 1, "editable": False, "refresh": "5m",
        "time": {"from": "now-24h", "to": "now"}, "panels": panels,
    }


# --- dashboards ----------------------------------------------------------------------------------------
cluster = dashboard(
    "opencost-olympians", "OpenCost / Cluster cost (olympians)",
    "Cloud-equivalent cost of the olympians cluster from OpenCost's exported metrics.",
    [
        stat(1, "Cluster cost / month", monthly(NODE_TOTAL), 0, 0,
             "All nodes' CPU + RAM at the configured prices, whether used or not."),
        stat(2, "Allocated compute / month", monthly(ALLOC), 6, 0,
             "CPU and memory requested by workloads, priced on the node they run on."),
        stat(3, "Idle compute / month", monthly(f"{NODE_TOTAL} - {ALLOC}"), 12, 0,
             "Node capacity nothing has requested: cluster cost minus allocated compute."),
        stat(4, "Storage / month", monthly(STORAGE), 18, 0,
             "Persistent volumes priced on their size (one price for every StorageClass)."),
        bars(5, "Compute cost by namespace / month", monthly(ALLOC_NS), "{{namespace}}", 0, 5, 12,
             "CPU + memory requests per namespace."),
        bars(6, "Storage cost by namespace / month", monthly(STORAGE_NS), "{{namespace}}", 12, 5, 12,
             "Persistent volume size x storage price, per claim namespace."),
        stacked(7, "Hourly compute cost by namespace", ALLOC_NS, "{{namespace}}", 15,
                "Allocated CPU + memory cost per hour, stacked."),
        table(8, "Node cost / month", [
            target(monthly(NODE_CPU), ref="CPU", instant=True, fmt="table"),
            target(monthly(NODE_RAM), ref="RAM", instant=True, fmt="table"),
            target(monthly("max by (node) (node_total_hourly_cost)"), ref="Total", instant=True, fmt="table"),
        ], {"node": "Node", "Value #CPU": "CPU", "Value #RAM": "RAM", "Value #Total": "Total"}, 24,
            "Per node: CPU capacity cost, RAM capacity cost and OpenCost's total.", "Total", h=7),
    ],
)

cost_centers = dashboard(
    "opencost-cost-centers-olympians", "OpenCost / Cost centers (olympians)",
    "Chargeback view: cloud-equivalent cost grouped by the cost-center label (pod/PVC label, else "
    "namespace label, else unallocated). Idle capacity is its own line.",
    [
        stat(1, "Charged to cost centers / month", monthly(f"{ALLOC} + {STORAGE}"), 0, 0,
             "Allocated compute + storage, all cost centers including unallocated.", w=8),
        stat(2, "Unallocated / month", monthly(UNALLOCATED), 8, 0,
             "Cost from pods, namespaces and PVCs with no cost-center label. Should be $0: label them.",
             w=8, color="orange"),
        stat(3, "Idle capacity / month", monthly(f"{NODE_TOTAL} - {ALLOC}"), 16, 0,
             "Node capacity nothing has requested. Not charged to any cost center.", w=8, color="purple"),
        bars(4, "Total cost by cost center / month", monthly(TOTAL_CC), "{{label_cost_center}}", 0, 5, 24,
             "Compute + storage per cost center.", h=7),
        bars(5, "Compute by cost center / month", monthly(COMPUTE_CC), "{{label_cost_center}}", 0, 12, 12,
             "CPU + memory requests, attributed by pod label, else namespace label."),
        bars(6, "Storage by cost center / month", monthly(STORAGE_CC), "{{label_cost_center}}", 12, 12, 12,
             "PV size x storage price, attributed by PVC label, else claim namespace label."),
        stacked(7, "Hourly cost by cost center", f"sum by (label_cost_center) (({COMPUTE_ATTR}) or ({STORAGE_ATTR}))",
                "{{label_cost_center}}", 22, "Compute + storage per hour, stacked by cost center."),
        table(8, "Chargeback by cost center and namespace / month", [
            target(monthly(COMPUTE_CC_NS), ref="Compute", instant=True, fmt="table"),
            target(monthly(STORAGE_CC_NS), ref="Storage", instant=True, fmt="table"),
        ], {"label_cost_center": "Cost center", "namespace": "Namespace",
            "Value #Compute": "Compute", "Value #Storage": "Storage"}, 31,
            "Each cost center's charges broken down by namespace.", "Compute", h=10),
    ],
)


def write(path, name, key, dash):
    body = json.dumps(dash, indent=2)
    with open(path, "w") as f:
        f.write("# GENERATED by opencost/hack/gen-dashboard.py; edit that script, not this file.\n")
        f.write("# Picked up by the kube-prometheus-stack Grafana sidecar (label grafana_dashboard=1, any namespace).\n")
        f.write(f"apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: {name}\n  namespace: opencost\n")
        f.write(f"  labels:\n    grafana_dashboard: \"1\"\ndata:\n  {key}: |\n")
        for line in body.splitlines():
            f.write("    " + line + "\n")
    print("wrote", os.path.relpath(path))


if __name__ == "__main__":
    base = os.path.join(HERE, "..", "base")
    write(os.path.join(base, "grafana-dashboard.yaml"), "opencost-grafana-dashboard",
          "opencost-cluster-cost.json", cluster)
    write(os.path.join(base, "grafana-dashboard-cost-centers.yaml"), "opencost-grafana-dashboard-cost-centers",
          "opencost-cost-centers.json", cost_centers)
