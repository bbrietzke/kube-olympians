include ../common.mk

# OpenCost: cost allocation from kube-prometheus-stack's metrics, with its cost metrics exported back
# to Prometheus for the Grafana dashboard. UI LAN-only at https://opencost.faultycloud.xyz.
# Helm only; needs monitoring/ first. See README.md.
NAMESPACE     := opencost
CHART_REPO    := https://opencost.github.io/opencost-helm-chart
CHART_VERSION := 2.5.35

.PHONY: prerequisites helm uninstall-helm

prerequisites: ## Apply the namespace and the Grafana dashboard ConfigMap
	$(call kapply,base)

helm: prerequisites ## Install or upgrade OpenCost (helm/values.yaml); waits for it and the UI route
	$(HELM) upgrade --install opencost opencost --repo $(CHART_REPO) --version $(CHART_VERSION) \
		-n $(NAMESPACE) -f helm/values.yaml --wait --timeout 10m
	$(WAIT_READY) -n $(NAMESPACE)
	$(KUBECTL) -n $(NAMESPACE) wait httproute --all --for=jsonpath='{.status.parents[0].conditions[?(@.type=="Accepted")].status}'=True --timeout=$(WAIT_TIMEOUT)

uninstall-helm: ## Remove OpenCost and its dashboard (cost history stays in Prometheus until retention)
	-$(HELM) uninstall opencost -n $(NAMESPACE) --wait
	-$(call kdelete,base)
