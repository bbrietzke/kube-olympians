include ../common.mk

NAMESPACE     := kube-system
CHART_REPO    := https://helm.cilium.io/
CHART_VERSION := 1.20.5

# Talos boots with no CNI (flannel and kube-proxy are disabled in ../talos_olympians), so Cilium
# is the first thing installed and replaces kube-proxy. It reaches the API server through
# KubePrism (localhost:7445), so it does not depend on the API endpoint (zeus, 192.168.3.9).
# Cilium is Helm-only here: the chart is the supported install and there is no kustomize route.

define wait_cilium
$(KUBECTL) -n $(NAMESPACE) rollout status daemonset/cilium --timeout=$(WAIT_TIMEOUT)
$(KUBECTL) -n $(NAMESPACE) rollout status deployment/cilium-operator --timeout=$(WAIT_TIMEOUT)
endef

.PHONY: helm olympians uninstall-olympians uninstall-helm

# Changing helm/values.yaml only updates the cilium-config ConfigMap: the chart does not restart
# the agents (rollOutCiliumPods defaults to false). To apply a change, restart them, one node at
# a time, with a short pod-traffic blip on each:
#   kubectl -n kube-system rollout restart daemonset/cilium deployment/cilium-operator
# For a change both ends of a connection must agree on (routing mode, encryption), restart every
# agent at once instead, so nodes spend seconds rather than minutes in mixed modes:
#   kubectl -n kube-system delete pod -l k8s-app=cilium
helm: ## Install or upgrade Cilium with Helm (helm/values.yaml); waits for the agents and operator
	$(HELM) upgrade --install cilium cilium --repo $(CHART_REPO) --version $(CHART_VERSION) \
		-n $(NAMESPACE) -f helm/values.yaml --wait
	$(wait_cilium)

olympians: ## Apply the LoadBalancer IP pool (192.168.3.200-204) and the L2 announcement policy (ens4f0)
	$(call wait_accepts,$(KUSTOMIZE) build overlays/olympians)
	$(call kapply,overlays/olympians)

uninstall-olympians: ## Remove the IP pool and L2 policy (LoadBalancer Services lose their IPs)
	-$(call kdelete,overlays/olympians)

# Removing the CNI leaves every node NotReady. The root Makefile never does this.
uninstall-helm: uninstall-olympians ## Remove Cilium entirely (the cluster has no pod networking afterwards)
	-$(HELM) uninstall cilium -n $(NAMESPACE) --wait
