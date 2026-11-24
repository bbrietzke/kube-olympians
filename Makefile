include common.mk

# Install order. Teardown runs in reverse.
#   cilium               - CNI (Helm only) + LoadBalancer IP pool and L2 announcements on ens4f0
#   external-snapshotter - VolumeSnapshot CRDs + controller (rook's CSI snapshots use them)
#   rook                 - Ceph cluster, hdd-pool / ssd-pool and their StorageClasses (rook-ceph-hdd is the default)
#   traefik              - Gateway API CRDs + Traefik ingress / gateway
#   certificateManager   - cert-manager + letsencrypt-dns01 ClusterIssuer (needs the Gateway API CRDs)
#   postgresql           - CloudNativePG operator (cluster00 is `make -C postgresql olympians`)
#   harbor               - container registry; manual (`make -C harbor helm`), needs cluster00 + traefik postCertManager
#   forgejo              - git forge + Actions runners; manual (`make -C forgejo helm runners`), needs cluster00 + traefik postCertManager
#
# Per-component targets: make -C <component> help

.PHONY: install helm uninstall uninstall-helm

install: ## Install every component with kustomize (Cilium with Helm), then apply the olympians config
	$(MAKE) -C cilium helm olympians
	$(MAKE) -C external-snapshotter install olympians
	$(MAKE) -C rook install olympians
	$(MAKE) -C traefik install
	$(MAKE) -C certificateManager install olympians
	$(MAKE) -C postgresql install

helm: ## Install every component with Helm where a chart exists (kustomize otherwise)
	$(MAKE) -C cilium helm olympians
	$(MAKE) -C external-snapshotter install olympians
	$(MAKE) -C rook helm olympians
	$(MAKE) -C traefik helm
	$(MAKE) -C certificateManager helm olympians
	$(MAKE) -C postgresql helm

# Neither teardown removes Cilium: without a CNI the nodes go NotReady and nothing can reschedule.
# Remove it on purpose with `make -C cilium uninstall-helm`.

uninstall: ## Tear down everything installed by `make install` (except Cilium)
	-$(MAKE) -C forgejo uninstall-helm
	-$(MAKE) -C harbor uninstall-helm
	-$(MAKE) -C postgresql uninstall
	-$(MAKE) -C certificateManager uninstall
	-$(MAKE) -C traefik uninstall
	-$(MAKE) -C rook uninstall
	-$(MAKE) -C external-snapshotter uninstall
	-$(MAKE) -C cilium uninstall-olympians

uninstall-helm: ## Tear down everything installed by `make helm` (except Cilium)
	-$(MAKE) -C forgejo uninstall-helm
	-$(MAKE) -C harbor uninstall-helm
	-$(MAKE) -C postgresql uninstall-helm
	-$(MAKE) -C certificateManager uninstall-helm
	-$(MAKE) -C traefik uninstall-helm
	-$(MAKE) -C rook uninstall-helm
	-$(MAKE) -C external-snapshotter uninstall
	-$(MAKE) -C cilium uninstall-olympians
