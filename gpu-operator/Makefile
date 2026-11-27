include ../common.mk

# NVIDIA GPU Operator for the workers' RTX 3050s. The driver and container toolkit come from Talos
# system extensions (../talos_olympians/schematic-gpu-worker.yaml), not from the operator.
# Helm only. See README.md.
NAMESPACE     := gpu-operator
CHART_REPO    := https://helm.ngc.nvidia.com/nvidia
CHART_VERSION := v26.7.3

.PHONY: prerequisites helm uninstall-helm smoke-test

prerequisites: ## Apply the gpu-operator namespace (PSA privileged)
	$(call kapply,base)

helm: prerequisites ## Install or upgrade the GPU Operator (helm/values.yaml) and wait for its pods
	$(HELM) upgrade --install gpu-operator gpu-operator --repo $(CHART_REPO) --version $(CHART_VERSION) \
		-n $(NAMESPACE) -f helm/values.yaml --wait --timeout 15m
	$(WAIT_READY) -n $(NAMESPACE)

smoke-test: ## Run nvidia-smi in a pod on a GPU node, print its output, then delete it
	-$(KUBECTL) -n $(NAMESPACE) delete pod gpu-smoke-test --ignore-not-found --wait
	$(KUBECTL) -n $(NAMESPACE) apply -f hack/smoke-test.yaml
	$(KUBECTL) -n $(NAMESPACE) wait pod gpu-smoke-test --for=jsonpath='{.status.phase}'=Succeeded --timeout=$(WAIT_TIMEOUT)
	$(KUBECTL) -n $(NAMESPACE) logs gpu-smoke-test
	$(KUBECTL) -n $(NAMESPACE) delete pod gpu-smoke-test --wait

uninstall-helm: ## Remove the GPU Operator and its namespace (the Talos driver stays)
	-$(HELM) uninstall gpu-operator -n $(NAMESPACE) --wait
	-$(call kdelete,base)
