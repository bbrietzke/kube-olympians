include ../common.mk

NAMESPACE     := harbor
CHART_REPO    := https://helm.goharbor.io
CHART_VERSION := 1.19.4
# Chart 1.19.4 (built for Harbor 2.15.4) with every image overridden to v2.16.0, the same version
# as on demigods. See helm/values.yaml.

DB_ENV_FILE    := base/harbor-db.env
ADMIN_ENV_FILE := base/harbor-admin.env

# Harbor needs CloudNativePG's cluster00 (postgresql olympians) and the Traefik Gateway with wildcard
# listeners (traefik postCertManager). Its "harbor" login role and database are separate
# DatabaseRole / Database objects in the db namespace, so cluster00 itself is never modified.
# The upstream chart relies on Helm `lookup` to keep its generated internal secrets stable across
# upgrades, so this component is Helm-only.

.PHONY: prerequisites helm password uninstall-helm

# 24 random alphanumerics plus "Aa1", which satisfies Harbor's password rules
# (8-128 chars with upper, lower and a digit) and needs no quoting anywhere.
define random_password
$$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 24)Aa1
endef

prerequisites: ## Generate the password files if missing; apply the harbor namespace, Secrets, and the "harbor" DatabaseRole + Database in cluster00; waits for both
	@test -f $(DB_ENV_FILE) || { printf 'username=harbor\npassword=%s\n' "$(call random_password)" > $(DB_ENV_FILE); \
		chmod 600 $(DB_ENV_FILE); echo "generated $(DB_ENV_FILE)"; }
	@test -f $(ADMIN_ENV_FILE) || { printf 'HARBOR_ADMIN_PASSWORD=%s\n' "$(call random_password)" > $(ADMIN_ENV_FILE); \
		chmod 600 $(ADMIN_ENV_FILE); echo "generated $(ADMIN_ENV_FILE)"; }
	@! grep -q REPLACE_ME $(DB_ENV_FILE) $(ADMIN_ENV_FILE) || { echo "replace REPLACE_ME in $(DB_ENV_FILE) / $(ADMIN_ENV_FILE)" >&2; exit 1; }
	@# The namespace must exist before the server-side dry run can validate the Secrets in it.
	$(KUBECTL) create namespace $(NAMESPACE) --dry-run=client -o yaml | $(KUBECTL) apply -f -
	$(call wait_accepts,$(KUSTOMIZE) build overlays/olympians)
	$(call kapply,overlays/olympians)
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

password: ## Print the Harbor admin password (user: admin)
	@sed -n 's/^HARBOR_ADMIN_PASSWORD=//p' $(ADMIN_ENV_FILE)

# The admin password is only read when Harbor first initialises its database. After that, change it
# in the Harbor UI (and update base/harbor-admin.env to match, for your own reference).
#
# uninstall-helm keeps the data: the chart's PVCs (resourcePolicy: keep), the harbor namespace and
# its Secrets, and the "harbor" database and role in cluster00 (both reclaim policies: retain).
# To remove them for good, see README.md "Uninstalling".

uninstall-helm: ## Remove the Harbor Helm release (keeps PVCs, Secrets and the database)
	-$(HELM) uninstall harbor -n $(NAMESPACE) --wait
