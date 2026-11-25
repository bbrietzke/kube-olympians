include ../common.mk

# Pocket ID at https://auth.brietzke.me: the OIDC login provider for brietzke.me apps. See README.md.
NAMESPACE := pocket-id
DB_ENV    := base/pocketid-db.env
APP_ENV   := base/pocket-id.env

.PHONY: prerequisites olympians publish unpublish uninstall

# One random DB password, written to both files so CloudNativePG's role and Pocket ID's connection
# string always agree. Generated once; delete both files to start over (only before first use).
prerequisites: ## Generate the git-ignored secrets if missing
	@test -f $(DB_ENV) -a -f $(APP_ENV) || { \
		pw=$$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32); \
		key=$$(openssl rand -base64 32); \
		printf 'username=pocketid\npassword=%s\n' "$$pw" > $(DB_ENV); \
		printf 'ENCRYPTION_KEY=%s\nDB_CONNECTION_STRING=postgres://pocketid:%s@cluster00-rw.db.svc:5432/pocketid?sslmode=require\n' "$$key" "$$pw" > $(APP_ENV); \
		chmod 600 $(DB_ENV) $(APP_ENV); echo "generated $(DB_ENV) and $(APP_ENV)"; }
	@! grep -q REPLACE_ME $(DB_ENV) $(APP_ENV) || { echo "replace REPLACE_ME in $(DB_ENV) / $(APP_ENV)" >&2; exit 1; }

olympians: prerequisites ## Deploy Pocket ID and its cluster00 database (no public route; see publish)
	$(KUBECTL) create namespace $(NAMESPACE) --dry-run=client -o yaml | $(KUBECTL) apply -f -
	$(call wait_accepts,$(KUSTOMIZE) build overlays/olympians)
	$(call kapply,overlays/olympians)
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
