include ../common.mk

NAMESPACE     := harbor
CHART_REPO    := https://helm.goharbor.io
CHART_VERSION := 1.19.4
# Chart 1.19.4 (built for Harbor 2.15.4) with every image overridden to v2.16.0, the same version
# as on demigods. See helm/values.yaml.

# Harbor needs CloudNativePG's cluster00 (postgresql olympians) and the Traefik Gateway with wildcard
# listeners (traefik postCertManager). Its "harbor" login role and database are separate
# DatabaseRole / Database objects in the db namespace, so cluster00 itself is never modified.
# The upstream chart relies on Helm `lookup` to keep its generated internal secrets stable across
# upgrades, so this component is Helm-only.

.PHONY: prerequisites helm password uninstall-helm

prerequisites: ## Apply the harbor namespace, its password ExternalSecrets (Bitwarden), and the "harbor" DatabaseRole + Database in cluster00; waits for all
	@# The namespace must exist before the server-side dry run can validate the Secrets in it.
	$(KUBECTL) create namespace $(NAMESPACE) --dry-run=client -o yaml | $(KUBECTL) apply -f -
	$(call wait_accepts,$(KUSTOMIZE) build overlays/olympians)
	$(call kapply,overlays/olympians)
	$(KUBECTL) -n db wait externalsecret/harbor-db-credentials --for=condition=Ready --timeout=$(WAIT_TIMEOUT)
	$(KUBECTL) -n $(NAMESPACE) wait externalsecret/harbor-database externalsecret/harbor-admin --for=condition=Ready --timeout=$(WAIT_TIMEOUT)
	@# The first reconcile can fail with "secrets ... is forbidden" until the operator has granted the
	@# instance access to the password Secret (~30s); it then retries. Wait for applied AND no message.
	@echo "waiting for databaserole/harbor to be applied with no error ..."; \
	for i in $$(seq 1 60); do \
		s=$$($(KUBECTL) -n db get databaserole harbor -o jsonpath='{.status.applied}|{.status.message}'); \
		[ "$$s" = "true|" ] && { echo "databaserole/harbor applied"; exit 0; }; \
		sleep 5; \
	done; \
	echo "databaserole/harbor not applied: $$s" >&2; exit 1
	$(KUBECTL) -n db wait database/harbor --for=jsonpath='{.status.applied}'=true --timeout=$(WAIT_TIMEOUT)

helm: prerequisites ## Install Harbor with Helm (helm/values.yaml); waits for every workload and the HTTPRoute
	$(HELM) upgrade --install harbor harbor --repo $(CHART_REPO) --version $(CHART_VERSION) \
		-n $(NAMESPACE) -f helm/values.yaml --wait --timeout 15m
	$(WAIT_READY) -n $(NAMESPACE)
	$(KUBECTL) -n $(NAMESPACE) wait httproute/harbor-route \
		--for=jsonpath='{.status.parents[0].conditions[?(@.type=="Accepted")].status}'=True --timeout=$(WAIT_TIMEOUT)

password: ## Print the Harbor admin password (user: admin), from its Secret (source: Bitwarden)
	@$(KUBECTL) -n $(NAMESPACE) get secret harbor-admin -o jsonpath='{.data.HARBOR_ADMIN_PASSWORD}' | base64 -d; echo

# The passwords come from Bitwarden (base/external-secrets.yaml, ExternalSecrets through the
# "bitwarden" ClusterSecretStore), so this needs external-secrets/ (helm + olympians) first.
# The admin password is only read when Harbor first initialises its database. After that, change it
# in the Harbor UI (and update harbor/harbor-admin/HARBOR_ADMIN_PASSWORD in Bitwarden to match).
#
# uninstall-helm keeps the data: the chart's PVCs (resourcePolicy: keep), the harbor namespace and
# its Secrets, and the "harbor" database and role in cluster00 (both reclaim policies: retain).
# To remove them for good, see README.md "Uninstalling".

uninstall-helm: ## Remove the Harbor Helm release (keeps PVCs, Secrets and the database)
	-$(HELM) uninstall harbor -n $(NAMESPACE) --wait
