# Monitoring: kube-prometheus-stack

Prometheus, Alertmanager and Grafana from [kube-prometheus-stack](https://github.com/prometheus-community/helm-charts/tree/main/charts/kube-prometheus-stack) (chart 93.11.0), plus node-exporter on every node and kube-state-metrics. **LAN only**, on `traefik-gateway`:

| UI | URL | Login |
| --- | --- | --- |
| Grafana | https://grafana.faultycloud.xyz | `make password` (user `admin`) |
| Prometheus | https://prometheus.faultycloud.xyz | none (LAN only) |
| Alertmanager | https://alertmanager.faultycloud.xyz | none (LAN only) |

| Task | Command (from `monitoring/`) |
| --- | --- |
| Install / upgrade | `make helm` (runs `prerequisites`: namespace and the Grafana admin Secret) |
| Grafana admin login | `make password` |
| Remove | `make uninstall-helm` (keeps the CRDs and the Prometheus/Alertmanager PVCs) |

## Design

| Part | Choice |
| --- | --- |
| Namespace | `monitoring`, Pod Security `privileged`: node-exporter needs the host network, PID namespace and root filesystem. Labeled for `traefik-gateway`. |
| Prometheus | 30 days of retention, capped at 45 GB, on a 50Gi `rook-ceph-ssd` volume. The TSDB's small random writes would be slow on the SMR HDDs. |
| Discovery | `*SelectorNilUsesHelmValues: false`: Prometheus picks up **every** ServiceMonitor, PodMonitor, Probe, ScrapeConfig and PrometheusRule in the cluster, not just the chart's own. Other components can ship their own monitors. |
| Alertmanager | 2Gi on SSD. **No receivers yet:** alerts show in its UI and in Grafana only. |
| Grafana | 5Gi on SSD for users and saved dashboards, with `Recreate` because the volume is ReadWriteOnce. The admin password is in git-ignored `base/grafana-admin.env`. The chart's 25 dashboards and both data sources are provisioned automatically. |
| Routes | The chart's own Gateway API support (`route.main`) creates the three HTTPRoutes on `traefik-gateway`. |

## Talos specifics
- **kube-proxy:** disabled, because Cilium replaces it.
- **Not scraped yet: kube-scheduler, kube-controller-manager and etcd.** On Talos they bind their metrics to `127.0.0.1` on zeus. Their scrapes and alert rules are off in `helm/values.yaml`. Enabling them needs a Talos control-plane patch: `bind-address: 0.0.0.0` for the scheduler and controller-manager, and etcd `listen-metrics-urls: http://0.0.0.0:2381`. Then turn the scrapes back on.

## Scraped (tested 2026-11-25)
All 26 targets were up:
- API server
- CoreDNS (2)
- kubelet (12: cAdvisor, probes, metrics, ×4 nodes)
- node-exporter (4)
- kube-state-metrics
- the stack's own Prometheus, Alertmanager, Grafana and operator

`Watchdog` always fires; that's the intended heartbeat.

## Next integrations (not done yet)
- **Rook/Ceph:** `monitoring.enabled: true` in the rook-ceph-cluster values adds its ServiceMonitor and Ceph alert rules.
- **CloudNativePG:** a PodMonitor for cluster00 (`monitoring.enablePodMonitor` on the Cluster) and the CNPG Grafana dashboard.
- **Cilium / Hubble:** `prometheus.enabled` and `serviceMonitor.enabled` in its values.
- **Traefik:** a metrics ServiceMonitor from its chart values.
- **Grafana login with Pocket ID** (generic OAuth), with callback `https://grafana.faultycloud.xyz/login/generic_oauth`.
- **An Alertmanager receiver** (email, Discord, a webhook…).
