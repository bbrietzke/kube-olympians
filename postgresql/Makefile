include ../common.mk

NAMESPACE     := cnpg-system
CHART_REPO    := https://cloudnative-pg.github.io/charts
CHART_VERSION := 0.29.2
# CloudNativePG v1.30.2 (kustomize manifest in overlays/install, chart 0.29.2 for Helm), plus the
# Barman Cloud plugin v0.16.0 (overlays/plugin-barman-cloud) on either route.

DB_NAMESPACE  := db
CLUSTER       := cluster00
# initdb plus two replicas cloning over the network can take a while.
PG_TIMEOUT    ?= 15m

# Backblaze B2 key for the Barman Cloud ObjectStore (git-ignored; see base/backblaze.env.example).
B2_ENV_FILE   := base/backblaze.env

# make snapshot / make b2backup: the Backup is named $(CLUSTER)[-b2]-$(SNAPSHOT_LABEL)-<UTC timestamp>.
SNAPSHOT_LABEL ?= adhoc
# Seconds to wait for an ad-hoc backup to complete.
SNAPSHOT_WAIT  ?= 600

.PHONY: install helm olympians snapshot b2backup snapshots uninstall uninstall-helm

install: ## Install the CloudNativePG operator and the Barman Cloud plugin (cnpg-system) via kustomize; waits for both
	$(call kinstall,overlays/install)
	$(call kinstall,overlays/plugin-barman-cloud)

helm: ## Install the CloudNativePG operator with Helm (helm/values.yaml) and the Barman Cloud plugin; waits for both
	$(HELM) upgrade --install cnpg cloudnative-pg --repo $(CHART_REPO) --version $(CHART_VERSION) \
		-n $(NAMESPACE) --create-namespace -f helm/values.yaml --wait
	$(WAIT_READY) -n $(NAMESPACE)
	$(call kinstall,overlays/plugin-barman-cloud)

# The namespace is created first so the server-side dry run (which waits for the operator's
# webhook to answer) can validate the namespaced Cluster.
olympians: ## Create the db namespace, the B2 key Secret, ObjectStore, cluster00 and its backup schedules; waits until Ready
	@grep -Eq '^ACCESS_KEY_ID=.+' $(B2_ENV_FILE) 2>/dev/null && grep -Eq '^ACCESS_SECRET_KEY=.+' $(B2_ENV_FILE) \
		&& ! grep -q 'REPLACE_ME' $(B2_ENV_FILE) || { \
		echo "$(B2_ENV_FILE) is missing or incomplete: cp $(B2_ENV_FILE).example $(B2_ENV_FILE) and fill in both keys." >&2; \
		exit 1; }
	$(KUBECTL) create namespace $(DB_NAMESPACE) --dry-run=client -o yaml | $(KUBECTL) apply -f -
	$(call wait_accepts,$(KUSTOMIZE) build overlays/olympians)
	$(call kapply,overlays/olympians)
	$(KUBECTL) -n $(DB_NAMESPACE) wait cluster/$(CLUSTER) --for=condition=Ready --timeout=$(PG_TIMEOUT)
	@$(MAKE) --no-print-directory b2-ready
	@if $(KUBECTL) -n $(DB_NAMESPACE) get backup -l cnpg.io/cluster=$(CLUSTER) \
		-o jsonpath='{range .items[?(@.spec.method=="plugin")]}{.status.phase}{"\n"}{end}' | grep -qx completed; then \
		echo "a completed B2 base backup already exists"; \
	else \
		echo "no completed B2 base backup yet; taking the first one"; \
		$(MAKE) --no-print-directory b2backup SNAPSHOT_LABEL=initial; \
	fi

# Wait until every instance runs the barman-cloud sidecar, all are Ready and WAL archiving to B2
# works. Adding the plugin rolls the instances one by one, so Ready alone is not enough.
.PHONY: b2-ready
b2-ready:
	@echo "waiting for the barman-cloud sidecar on every instance and WAL archiving to B2 ..."; \
	for i in $$(seq 1 180); do \
		want=$$($(KUBECTL) -n $(DB_NAMESPACE) get cluster $(CLUSTER) -o jsonpath='{.spec.instances}'); \
		ready=$$($(KUBECTL) -n $(DB_NAMESPACE) get cluster $(CLUSTER) -o jsonpath='{.status.readyInstances}'); \
		arch=$$($(KUBECTL) -n $(DB_NAMESPACE) get cluster $(CLUSTER) -o jsonpath='{.status.conditions[?(@.type=="ContinuousArchiving")].status}'); \
		side=$$($(KUBECTL) -n $(DB_NAMESPACE) get pods -l cnpg.io/cluster=$(CLUSTER),cnpg.io/podRole=instance \
			-o jsonpath='{range .items[*]}{range .spec.initContainers[*]}{.name}{"\n"}{end}{range .spec.containers[*]}{.name}{"\n"}{end}{end}' \
			| grep -cx plugin-barman-cloud); \
		[ -n "$$want" ] && [ "$$ready" = "$$want" ] && [ "$$side" = "$$want" ] && [ "$$arch" = "True" ] && { echo "ready: $$ready/$$want instances, sidecars $$side, archiving $$arch"; exit 0; }; \
		sleep 5; \
	done; \
	echo "timed out waiting for B2 archiving; check: kubectl -n $(DB_NAMESPACE) describe cluster $(CLUSTER)" >&2; exit 1

# $(call adhoc_backup,<overlay>,<placeholder name>,<name prefix>,<kinds to show when done>)
# Creates a new Backup from the overlay under a unique name, then polls until CNPG reports
# completed (exit 0) or failed (exit 1).
define adhoc_backup
@echo "$(SNAPSHOT_LABEL)" | grep -Eq '^[a-z0-9]([a-z0-9-]{0,20}[a-z0-9])?$$' || { \
	echo "SNAPSHOT_LABEL must be 1-22 chars of a-z, 0-9 and '-' (got '$(SNAPSHOT_LABEL)')" >&2; exit 1; }
@name=$(3)-$(SNAPSHOT_LABEL)-$$(date -u +%Y%m%d%H%M%S); \
$(KUSTOMIZE) build $(1) \
	| sed "s/^  name: $(2)$$/  name: $$name/" \
	| $(KUBECTL) create -f - || exit 1; \
echo "waiting up to $(SNAPSHOT_WAIT)s for backup/$$name ..."; \
for i in $$(seq 1 $$(( $(SNAPSHOT_WAIT) / 5 ))); do \
	phase=$$($(KUBECTL) -n $(DB_NAMESPACE) get backup $$name -o jsonpath='{.status.phase}'); \
	case "$$phase" in \
	completed) $(KUBECTL) -n $(DB_NAMESPACE) get $(4) $$name; exit 0 ;; \
	failed) $(KUBECTL) -n $(DB_NAMESPACE) get backup $$name -o jsonpath='{.status.error}{"\n"}' >&2; exit 1 ;; \
	esac; \
	sleep 5; \
done; \
echo "timed out; check: kubectl -n $(DB_NAMESPACE) describe backup $$name" >&2; exit 1
endef

# The standby a snapshot runs on rejoins about 30s after it completes.
snapshot: ## Take an ad-hoc volume-snapshot backup of cluster00 now (SNAPSHOT_LABEL=pre-upgrade to tag it); waits for it
	$(call adhoc_backup,overlays/snapshot,$(CLUSTER)-snapshot-placeholder,$(CLUSTER),backup$(comma)volumesnapshot)

b2backup: ## Take an ad-hoc base backup of cluster00 to Backblaze B2 now (SNAPSHOT_LABEL=pre-upgrade to tag it); waits for it
	$(call adhoc_backup,overlays/b2backup,$(CLUSTER)-b2-placeholder,$(CLUSTER)-b2,backup)

snapshots: ## List cluster00's backups (snapshot and B2, scheduled and ad-hoc), VolumeSnapshots and WAL archiving status
	$(KUBECTL) -n $(DB_NAMESPACE) get backup -l cnpg.io/cluster=$(CLUSTER) --sort-by=.metadata.creationTimestamp
	$(KUBECTL) -n $(DB_NAMESPACE) get volumesnapshot -l cnpg.io/cluster=$(CLUSTER) --sort-by=.metadata.creationTimestamp
	@$(KUBECTL) -n $(DB_NAMESPACE) get cluster $(CLUSTER) \
		-o jsonpath='{range .status.conditions[?(@.type=="ContinuousArchiving")]}WAL archiving to B2: {.status} ({.reason}){"\n"}{end}'

comma := ,

# Deleting the Cluster deletes its PVCs, and rook-ceph-ssd's Delete reclaim policy removes the
# RBD images with them: uninstall destroys the database data. Deleting the db namespace also
# deletes every Backup and VolumeSnapshot in it, so the snapshot backups go too. Backups in
# Backblaze B2 are NOT touched by uninstall; they expire through the ObjectStore retention only
# while a cluster is still archiving there.
#
# Install external-snapshotter before this operator. If the snapshot CRDs are added later,
# restart it (kubectl -n cnpg-system rollout restart deploy/cnpg-controller-manager) or
# method: volumeSnapshot backups are rejected.

uninstall: ## Remove cluster00, the db namespace, the Barman Cloud plugin and the kustomize operator install (deletes the CNPG CRDs)
	-$(call kdelete,overlays/olympians)
	-$(call kdelete,overlays/plugin-barman-cloud)
	-$(call kdelete,overlays/install)

uninstall-helm: ## Remove cluster00, the db namespace, the Barman Cloud plugin and the Helm release
	-$(call kdelete,overlays/olympians)
	-$(call kdelete,overlays/plugin-barman-cloud)
	-$(HELM) uninstall cnpg -n $(NAMESPACE) --wait
	-$(KUBECTL) delete namespace $(NAMESPACE) --ignore-not-found
