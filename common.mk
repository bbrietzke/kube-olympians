# Shared settings and helpers for every component Makefile.
# Included by <component>/Makefile as `include ../common.mk`.

# Repo root, resolved when common.mk is included (it is the last makefile read at that point).
ROOT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

# Every kubectl and helm call targets this context, whatever `kubectl config current-context`
# says, so a target can never land on another cluster (demigods shares this kubeconfig).
KUBE_CONTEXT ?= admin@olympians

KUBECTL   ?= kubectl --context $(KUBE_CONTEXT)
KUSTOMIZE ?= kustomize
HELM      ?= helm --kube-context $(KUBE_CONTEXT)

# How long to wait for each CRD / workload to become ready.
WAIT_TIMEOUT ?= 300s
export KUBECTL WAIT_TIMEOUT

# <manifests> | $(WAIT_READY)       wait for the CRDs and workloads in those manifests
# $(WAIT_READY) -n <namespace>      wait for every workload in a namespace
WAIT_READY := $(ROOT_DIR)/hack/wait-ready.sh

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show the targets this component supports
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# $(call kapply,<overlay dir>) - build an overlay and server-side apply it.
# Server-side apply avoids the 256KiB last-applied annotation limit hit by large CRDs.
define kapply
$(KUSTOMIZE) build $(1) | $(KUBECTL) apply --server-side --force-conflicts -f -
endef

# $(call kdelete,<overlay dir>) - build an overlay and delete what it renders.
define kdelete
$(KUSTOMIZE) build $(1) | $(KUBECTL) delete --ignore-not-found -f -
endef

# $(call kinstall,<overlay dir>) - apply an overlay, then wait for its CRDs and workloads.
define kinstall
$(call kapply,$(1))
$(KUSTOMIZE) build $(1) | $(WAIT_READY)
endef

# $(call wait_accepts,<command that prints manifests>) - retry a server-side dry run of those
# manifests until the API server (and any admission webhooks) accept them. Gives up after ~5 minutes.
#   e.g. $(call wait_accepts,$(KUSTOMIZE) build overlays/olympians)
define wait_accepts
@echo "waiting for the API server to accept: $(1)"; \
for i in $$(seq 1 60); do \
  $(1) | $(KUBECTL) apply --server-side --force-conflicts --dry-run=server -f - >/dev/null 2>&1 && exit 0; \
  sleep 5; \
done; \
echo "timed out waiting for the API server to accept: $(1)" >&2; \
$(1) | $(KUBECTL) apply --server-side --force-conflicts --dry-run=server -f -
endef
