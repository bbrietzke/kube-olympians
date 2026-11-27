include ../common.mk

# kube-prometheus-stack: Prometheus, Alertmanager and Grafana, LAN-only at
# https://{prometheus,alertmanager,grafana}.faultycloud.xyz. Helm only. See README.md.
NAMESPACE     := monitoring
CHART_REPO    := https://prometheus-community.github.io/helm-charts
CHART_VERSION := 93.11.0
# Grafana's admin login and the Pushover credentials come from Bitwarden
# (base/external-secrets.yaml), so this needs external-secrets/ (helm + olympians) first.

.PHONY: prerequisites helm password uninstall-helm

prerequisites: ## Apply the namespace and the Grafana admin + Pushover ExternalSecrets (Bitwarden); waits for them
	$(call kapply,base)
	$(KUBECTL) -n $(NAMESPACE) wait externalsecret/grafana-admin externalsecret/alertmanager-pushover --for=condition=Ready --timeout=$(WAIT_TIMEOUT)

# --wait covers the operator, Grafana and kube-state-metrics; Prometheus and Alertmanager are created
# by the operator afterwards, so wait for their StatefulSets and for the routes too.
helm: prerequisites ## Install or upgrade kube-prometheus-stack (helm/values.yaml); waits for everything
	$(HELM) upgrade --install kube-prometheus-stack kube-prometheus-stack --repo $(CHART_REPO) --version $(CHART_VERSION) \
		-n $(NAMESPACE) -f helm/values.yaml --wait --timeout 10m
	$(KUBECTL) -n $(NAMESPACE) wait --for=create statefulset/prometheus-kube-prometheus-stack-prometheus statefulset/alertmanager-kube-prometheus-stack-alertmanager --timeout=$(WAIT_TIMEOUT)
	$(WAIT_READY) -n $(NAMESPACE)
	$(KUBECTL) -n $(NAMESPACE) wait httproute --all --for=jsonpath='{.status.parents[0].conditions[?(@.type=="Accepted")].status}'=True --timeout=$(WAIT_TIMEOUT)

password: ## Print the Grafana admin login, from its Secret (source: Bitwarden)
	@printf 'username: '; $(KUBECTL) -n $(NAMESPACE) get secret grafana-admin -o jsonpath='{.data.admin-user}' | base64 -d; echo
	@printf 'password: '; $(KUBECTL) -n $(NAMESPACE) get secret grafana-admin -o jsonpath='{.data.admin-password}' | base64 -d; echo

# Helm doesn't delete CRDs, so ServiceMonitors etc. elsewhere survive an uninstall. The PVCs from
# the Prometheus/Alertmanager StatefulSets are kept too (delete them to drop the metrics history).
uninstall-helm: ## Remove the release (keeps the CRDs and the Prometheus/Alertmanager PVCs)
	-$(HELM) uninstall kube-prometheus-stack -n $(NAMESPACE) --wait
