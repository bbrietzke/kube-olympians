#!/usr/bin/env python3
"""Generate opencost/base/grafana-dashboard.yaml: a Grafana dashboard (as a ConfigMap picked up by
the kube-prometheus-stack Grafana sidecar, label grafana_dashboard=1) built only from OpenCost's
exported metrics plus kube-state-metrics. Re-run after editing: python3 opencost/hack/gen-dashboard.py

Notes on the queries:
- OpenCost's series are deduplicated with max by (...): after an OpenCost restart the old pod's
  series linger for Prometheus's 5m lookback, which would otherwise double every cost.
- "Allocated" is CPU/RAM requests (OpenCost's container_*_allocation) priced per node; "idle" is
  node cost minus allocated compute. Storage is priced on each PV's size (pv_hourly_cost is per
  GiB-hour), mapped to the claim's namespace via kube_persistentvolume_claim_ref.
- Prices are cloud-equivalent (see opencost/helm/values.yaml), so these are "what this would cost in
  a public cloud", not the home bill.
"""
import json
import os

HOURS_PER_MONTH = 730
DS = {"type": "prometheus", "uid": "prometheus"}

NODE_TOTAL = "sum(max by (node) (node_total_hourly_cost))"
ALLOC_NS = (
    "sum by (namespace) ("
    " max by (namespace, pod, container, node) (container_cpu_allocation)"
    " * on (node) group_left () max by (node) (node_cpu_hourly_cost)"
    " + max by (namespace, pod, container, node) (container_memory_allocation_bytes) / 1073741824"
    " * on (node) group_left () max by (node) (node_ram_hourly_cost)"
    ")"
)
ALLOC = f"sum({ALLOC_NS})"
PV_COST = (
    "max by (persistentvolume) (pv_hourly_cost)"
    " * on (persistentvolume) group_left () max by (persistentvolume) (kube_persistentvolume_capacity_bytes) / 1073741824"
)
STORAGE = f"sum({PV_COST})"
STORAGE_NS = (
    "sum by (namespace) (label_replace("
    f" {PV_COST} * on (persistentvolume) group_left (claim_namespace)"
    " max by (persistentvolume, claim_namespace) (kube_persistentvolume_claim_ref),"
    ' "namespace", "$1", "claim_namespace", "(.*)"))'
)
NODE_CPU = "max by (node) (node_cpu_hourly_cost) * on (node) max by (node) (kube_node_status_capacity{resource=\"cpu\"})"
NODE_RAM = "max by (node) (node_ram_hourly_cost) * on (node) max by (node) (kube_node_status_capacity{resource=\"memory\"}) / 1073741824"


def monthly(expr):
    return f"({expr}) * {HOURS_PER_MONTH}"


def target(expr, legend="", ref="A", instant=False, fmt="time_series"):
    t = {"datasource": DS, "expr": expr, "legendFormat": legend, "refId": ref, "format": fmt}
    if instant:
        t.update({"instant": True, "range": False})
    return t


def stat(pid, title, expr, x, desc):
    return {
        "id": pid, "type": "stat", "title": title, "description": desc, "datasource": DS,
        "gridPos": {"h": 5, "w": 6, "x": x, "y": 0},
        "targets": [target(expr, instant=True)],
        "fieldConfig": {"defaults": {"unit": "currencyUSD", "decimals": 0,
                                     "color": {"mode": "fixed", "fixedColor": "blue"}}, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "value", "graphMode": "none",
                    "textMode": "value"},
    }


def bars(pid, title, expr, legend, y, x, w, desc):
    return {
        "id": pid, "type": "bargauge", "title": title, "description": desc, "datasource": DS,
        "gridPos": {"h": 10, "w": w, "x": x, "y": y},
        "targets": [target(f"sort_desc({expr})", legend, instant=True)],
        "fieldConfig": {"defaults": {"unit": "currencyUSD", "decimals": 2, "min": 0,
                                     "color": {"mode": "continuous-BlYlRd"}}, "overrides": []},
        "options": {"orientation": "horizontal", "displayMode": "gradient", "showUnfilled": True,
                    "reduceOptions": {"calcs": ["lastNotNull"]}, "valueMode": "color"},
    }


panels = [
    stat(1, "Cluster cost / month", monthly(NODE_TOTAL), 0,
         "All nodes' CPU + RAM at the configured prices, whether used or not."),
    stat(2, "Allocated compute / month", monthly(ALLOC), 6,
         "CPU and memory requested by workloads, priced on the node they run on."),
    stat(3, "Idle compute / month", monthly(f"{NODE_TOTAL} - {ALLOC}"), 12,
         "Node capacity nothing has requested: cluster cost minus allocated compute."),
    stat(4, "Storage / month", monthly(STORAGE), 18,
         "Persistent volumes priced on their size (one price for every StorageClass)."),
    bars(5, "Compute cost by namespace / month", monthly(ALLOC_NS), "{{namespace}}", 5, 0, 12,
         "CPU + memory requests per namespace."),
    bars(6, "Storage cost by namespace / month", monthly(STORAGE_NS), "{{namespace}}", 5, 12, 12,
         "Persistent volume size x storage price, per claim namespace."),
    {
        "id": 7, "type": "timeseries", "title": "Hourly compute cost by namespace", "datasource": DS,
        "description": "Allocated CPU + memory cost per hour, stacked.",
        "gridPos": {"h": 9, "w": 24, "x": 0, "y": 15},
        "targets": [target(ALLOC_NS, "{{namespace}}")],
        "fieldConfig": {"defaults": {"unit": "currencyUSD", "decimals": 3,
                                     "custom": {"stacking": {"mode": "normal"}, "fillOpacity": 30}},
                        "overrides": []},
        "options": {"legend": {"displayMode": "table", "placement": "right", "calcs": ["lastNotNull", "mean"]},
                    "tooltip": {"mode": "multi", "sort": "desc"}},
    },
    {
        "id": 8, "type": "table", "title": "Node cost / month", "datasource": DS,
        "description": "Per node: CPU capacity cost, RAM capacity cost and OpenCost's total.",
        "gridPos": {"h": 7, "w": 24, "x": 0, "y": 24},
        "targets": [
            target(monthly(NODE_CPU), ref="CPU", instant=True, fmt="table"),
            target(monthly(NODE_RAM), ref="RAM", instant=True, fmt="table"),
            target(monthly("max by (node) (node_total_hourly_cost)"), ref="Total", instant=True, fmt="table"),
        ],
        "transformations": [
            {"id": "merge", "options": {}},
            {"id": "organize", "options": {
                "excludeByName": {"Time": True},
                "renameByName": {"node": "Node", "Value #CPU": "CPU", "Value #RAM": "RAM", "Value #Total": "Total"}}},
        ],
        "fieldConfig": {"defaults": {"unit": "currencyUSD", "decimals": 2}, "overrides": []},
        "options": {"showHeader": True, "sortBy": [{"displayName": "Total", "desc": True}]},
    },
]

dashboard = {
    "uid": "opencost-olympians",
    "title": "OpenCost / Cluster cost (olympians)",
    "description": "Cloud-equivalent cost of the olympians cluster from OpenCost's exported metrics.",
    "tags": ["opencost", "cost"],
    "timezone": "browser",
    "schemaVersion": 39,
    "version": 1,
    "editable": False,
    "refresh": "5m",
    "time": {"from": "now-24h", "to": "now"},
    "panels": panels,
}

out = os.path.join(os.path.dirname(__file__), "..", "base", "grafana-dashboard.yaml")
body = json.dumps(dashboard, indent=2)
with open(out, "w") as f:
    f.write("# GENERATED by opencost/hack/gen-dashboard.py; edit that script, not this file.\n")
    f.write("# Picked up by the kube-prometheus-stack Grafana sidecar (label grafana_dashboard=1, any namespace).\n")
    f.write("apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: opencost-grafana-dashboard\n  namespace: opencost\n")
    f.write("  labels:\n    grafana_dashboard: \"1\"\ndata:\n  opencost-cluster-cost.json: |\n")
    for line in body.splitlines():
        f.write("    " + line + "\n")
print("wrote", os.path.normpath(out))
