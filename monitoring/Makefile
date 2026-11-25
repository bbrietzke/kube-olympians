include ../common.mk

# kube-prometheus-stack: Prometheus, Alertmanager and Grafana, LAN-only at
# https://{prometheus,alertmanager,grafana}.faultycloud.xyz. Helm only. See README.md.
NAMESPACE     := monitoring
CHART_REPO    := https://prometheus-community.github.io/helm-charts
CHART_VERSION := 93.11.0
ADMIN_ENV     := base/grafana-admin.env

.PHONY: prerequisites helm password uninstall-helm

prerequisites: ## Generate the Grafana admin password if missing; apply the namespace and its Secret
	@test -f $(ADMIN_ENV) || { printf 'admin-user=admin\nadmin-password=%s\n' "$$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 24)" > $(ADMIN_ENV); \
		chmod 600 $(ADMIN_ENV); echo "generated $(ADMIN_ENV)"; }
	@! grep -q REPLACE_ME $(ADMIN_ENV) || { echo "replace REPLACE_ME in $(ADMIN_ENV)" >&2; exit 1; }
	$(call kapply,base)

# --wait covers the operator, Grafana and kube-state-metrics; Prometheus and Alertmanager are created
# by the operator afterwards, so wait for their StatefulSets and for the routes too.
helm: prerequisites ## Install or upgrade kube-prometheus-stack (helm/values.yaml); waits for everything
	$(HELM) upgrade --install kube-prometheus-stack kube-prometheus-stack --repo $(CHART_REPO) --version $(CHART_VERSION) \
		-n $(NAMESPACE) -f helm/values.yaml --wait --timeout 10m
	$(KUBECTL) -n $(NAMESPACE) wait --for=create statefulset/prometheus-kube-prometheus-stack-prometheus statefulset/alertmanager-kube-prometheus-stack-alertmanager --timeout=$(WAIT_TIMEOUT)
	$(WAIT_READY) -n $(NAMESPACE)
	$(KUBECTL) -n $(NAMESPACE) wait httproute --all --for=jsonpath='{.status.parents[0].conditions[?(@.type=="Accepted")].status}'=True --timeout=$(WAIT_TIMEOUT)

password: ## Print the Grafana admin login
	@sed -n 's/^admin-user=/username: /p; s/^admin-password=/password: /p' $(ADMIN_ENV)

# Helm doesn't delete CRDs, so ServiceMonitors etc. elsewhere survive an uninstall. The PVCs from
# the Prometheus/Alertmanager StatefulSets are kept too (delete them to drop the metrics history).
uninstall-helm: ## Remove the release (keeps the CRDs and the Prometheus/Alertmanager PVCs)
	-$(HELM) uninstall kube-prometheus-stack -n $(NAMESPACE) --wait
