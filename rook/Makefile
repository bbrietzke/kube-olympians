include ../common.mk

NAMESPACE     := rook-ceph
CHART_REPO    := https://charts.rook.io/release
CHART_VERSION := v1.21.2
# Bringing up mons, mgr and six OSDs (two per worker, one on an SMR HDD) can take a while.
CEPH_TIMEOUT  ?= 30m

# Wait until the CephCluster is Ready, the RBD CSI driver is registered and every
# workload in the namespace (mons, mgr, OSDs, CSI plugins) has rolled out.
define wait_ceph
$(KUBECTL) -n $(NAMESPACE) wait cephcluster/rook-ceph --for=jsonpath='{.status.phase}'=Ready --timeout=$(CEPH_TIMEOUT)
$(KUBECTL) wait --for=create csidriver/rook-ceph.rbd.csi.ceph.com --timeout=$(WAIT_TIMEOUT)
$(WAIT_READY) -n $(NAMESPACE)
endef

.PHONY: prerequisites install helm olympians toolbox uninstall uninstall-helm

prerequisites: ## Install the Rook CRDs, common RBAC and the ceph-csi operator
	$(call kinstall,overlays/prerequisites)

install: prerequisites ## Install the Rook operator and the CephCluster via kustomize; waits for a Ready cluster
	$(call kinstall,overlays/install)
	$(wait_ceph)

# Talos enforces Pod Security Admission; Ceph's pods need the namespace labeled privileged.
# (The kustomize route sets the same labels in overlays/prerequisites.)
helm: ## Install the Rook operator and the CephCluster with Helm; waits for a Ready cluster
	$(KUBECTL) create namespace $(NAMESPACE) --dry-run=client -o yaml | $(KUBECTL) apply -f -
	$(KUBECTL) label namespace $(NAMESPACE) --overwrite pod-security.kubernetes.io/enforce=privileged \
		pod-security.kubernetes.io/audit=privileged pod-security.kubernetes.io/warn=privileged
	$(HELM) upgrade --install rook-ceph rook-ceph --repo $(CHART_REPO) --version $(CHART_VERSION) \
		-n $(NAMESPACE) -f helm/operator.yaml --wait
	@# The chart does not create the ceph-csi OperatorConfig / Driver objects; see helm/csi-drivers.yaml.
	$(KUBECTL) apply --server-side --force-conflicts -f helm/csi-drivers.yaml
	$(HELM) upgrade --install rook-ceph-cluster rook-ceph-cluster --repo $(CHART_REPO) --version $(CHART_VERSION) \
		-n $(NAMESPACE) -f helm/cluster.yaml
	$(wait_ceph)

olympians: ## Apply hdd-pool + the default rook-ceph-hdd StorageClass and ssd-pool + rook-ceph-ssd; waits for both pools
	$(call kapply,overlays/olympians)
	$(KUBECTL) -n $(NAMESPACE) wait cephblockpool/hdd-pool cephblockpool/ssd-pool --for=jsonpath='{.status.phase}'=Ready --timeout=$(WAIT_TIMEOUT)

toolbox: ## Deploy the rook-ceph-tools pod
	$(call kinstall,overlays/toolbox)

# Teardown order matters: pools before the cluster, the cluster before the operator
# (or the CephCluster finalizer is never removed), and the CRDs last.
# Data on the OSD drives is NOT wiped; see Rook's cleanupPolicy docs for that.

uninstall: ## Remove toolbox, pools, CephCluster, operator and CRDs (kustomize route)
	-$(call kdelete,overlays/toolbox)
	-$(call kdelete,overlays/olympians)
	-$(KUBECTL) -n $(NAMESPACE) delete cephcluster rook-ceph --ignore-not-found --timeout=10m
	-$(call kdelete,overlays/install)
	-$(call kdelete,overlays/prerequisites)

uninstall-helm: ## Remove toolbox, pools and both Helm releases (Helm route)
	-$(call kdelete,overlays/toolbox)
	-$(call kdelete,overlays/olympians)
	-$(HELM) uninstall rook-ceph-cluster -n $(NAMESPACE) --wait
	-$(KUBECTL) delete --ignore-not-found -f helm/csi-drivers.yaml
	-$(HELM) uninstall rook-ceph -n $(NAMESPACE) --wait
