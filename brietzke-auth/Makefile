include ../common.mk

# Pocket ID at https://auth.brietzke.me: the OIDC login provider for brietzke.me apps. See README.md.
NAMESPACE := pocket-id
# The DB password and ENCRYPTION_KEY come from Bitwarden (base/external-secrets.yaml), so this
# needs external-secrets/ (helm + olympians) first.

.PHONY: olympians publish unpublish uninstall

olympians: ## Deploy Pocket ID, its ExternalSecrets (Bitwarden) and its cluster00 database (no public route; see publish)
	$(KUBECTL) create namespace $(NAMESPACE) --dry-run=client -o yaml | $(KUBECTL) apply -f -
	$(call wait_accepts,$(KUSTOMIZE) build overlays/olympians)
	$(call kapply,overlays/olympians)
	$(KUBECTL) -n db wait externalsecret/pocketid-db-credentials --for=condition=Ready --timeout=$(WAIT_TIMEOUT)
	$(KUBECTL) -n $(NAMESPACE) wait externalsecret/pocket-id-secrets --for=condition=Ready --timeout=$(WAIT_TIMEOUT)
	@# As with harbor/forgejo, the role's first reconcile can fail ("secrets ... is forbidden") for
	@# ~30s until the operator can read the password Secret. Wait for applied AND no message.
	@echo "waiting for databaserole/pocketid to be applied with no error ..."; \
	for i in $$(seq 1 60); do \
		s=$$($(KUBECTL) -n db get databaserole pocketid -o jsonpath='{.status.applied}|{.status.message}'); \
		[ "$$s" = "true|" ] && { echo "databaserole/pocketid applied"; exit 0; }; \
		sleep 5; \
	done; \
	echo "databaserole/pocketid not applied: $$s" >&2; exit 1
	$(KUBECTL) -n db wait database/pocketid --for=jsonpath='{.status.applied}'=true --timeout=$(WAIT_TIMEOUT)
	@# envFrom is read only at start, and ESO doesn't roll pods, so restart to pick up any change.
	$(KUBECTL) -n $(NAMESPACE) rollout restart deployment/pocket-id
	$(KUBECTL) -n $(NAMESPACE) rollout status deployment/pocket-id --timeout=$(WAIT_TIMEOUT)

publish: ## Make auth.brietzke.me public. Claim the admin at https://auth.brietzke.me/setup right away
	$(call kapply,overlays/public)
	$(KUBECTL) -n $(NAMESPACE) wait httproute/pocket-id --for=jsonpath='{.status.parents[0].conditions[?(@.type=="Accepted")].status}'=True --timeout=$(WAIT_TIMEOUT)
	@echo "Now open https://auth.brietzke.me/setup and create your admin account (passkey)."

unpublish: ## Remove the public route (Pocket ID keeps running, unreachable)
	-$(call kdelete,overlays/public)

# The database and role are kept (reclaim policy retain), like harbor and forgejo. See README.md.
uninstall: unpublish ## Remove Pocket ID (keeps the pocketid database and role in cluster00)
	-$(call kdelete,overlays/olympians)
