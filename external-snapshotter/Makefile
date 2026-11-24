include ../common.mk

# There is no upstream Helm chart for external-snapshotter, so this component is kustomize-only.

.PHONY: prerequisites install olympians uninstall

prerequisites: ## Install the VolumeSnapshot CRDs
	$(call kinstall,overlays/prerequisites)

# Install this before rook (the root Makefile does). If rook is already running, restart its CSI
# controllers afterwards so the csi-snapshotter sidecars pick up the new CRDs:
#   kubectl -n rook-ceph rollout restart deploy/rook-ceph.rbd.csi.ceph.com-ctrlplugin deploy/rook-ceph.cephfs.csi.ceph.com-ctrlplugin
install: prerequisites ## Install the snapshot-controller (kube-system)
	$(call kinstall,overlays/install)

olympians: ## Apply the rook-ceph-snapclass VolumeSnapshotClass
	$(call kapply,overlays/olympians)

uninstall: ## Remove the snapshot class, the controller and the CRDs (deletes ALL VolumeSnapshots)
	-$(call kdelete,overlays/olympians)
	-$(call kdelete,overlays/install)
	-$(call kdelete,overlays/prerequisites)
