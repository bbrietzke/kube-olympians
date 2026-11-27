include ../common.mk

NAMESPACE     := forgejo
CHART         := oci://code.forgejo.org/forgejo-helm/forgejo
CHART_VERSION := 17.3.3
# Chart 17.3.3 ships Forgejo 15.0.12 (LTS, supported until 2027-07-15). Runners: forgejo-runner
# 13.2.2 (overlays/runners). All images are multi-arch (the olympians nodes are amd64).

RUNNERS         := 0 1

# Needs CloudNativePG's cluster00 (postgresql olympians) and the Traefik Gateway with wildcard
# listeners (traefik postCertManager). Its "forgejo" role and database are separate DatabaseRole /
# Database objects in the db namespace; cluster00 itself is never modified.

.PHONY: prerequisites helm runners password uninstall-helm

# The credentials come from Bitwarden (base/external-secrets.yaml: ExternalSecrets through the
# "bitwarden" ClusterSecretStore), so this needs external-secrets/ (helm + olympians) first.
# To add a runner, add its token-N / uuid-N to Bitwarden and to the forgejo-runner ExternalSecret.
# A runner token is 40 hex chars; its UUID is the first 16 chars as hex-encoded ASCII (8-4-4-4-12).
RUNNER_SECRET = $(KUBECTL) -n $(NAMESPACE) get secret forgejo-runner -o jsonpath="{.data.$(1)}" | base64 -d

prerequisites: ## Apply the forgejo namespace, its credential ExternalSecrets (Bitwarden), and the "forgejo" DatabaseRole + Database in cluster00; waits for all
	@# The namespace must exist before the server-side dry run can validate the Secrets in it.
	$(KUBECTL) create namespace $(NAMESPACE) --dry-run=client -o yaml | $(KUBECTL) apply -f -
	$(call wait_accepts,$(KUSTOMIZE) build overlays/olympians)
	$(call kapply,overlays/olympians)
	$(KUBECTL) -n db wait externalsecret/forgejo-db-credentials --for=condition=Ready --timeout=$(WAIT_TIMEOUT)
	$(KUBECTL) -n $(NAMESPACE) wait externalsecret/forgejo-database externalsecret/forgejo-admin externalsecret/forgejo-runner --for=condition=Ready --timeout=$(WAIT_TIMEOUT)
	@# The first reconcile can fail with "secrets ... is forbidden" until the operator has granted the
	@# instance access to the password Secret (~30s); it then retries. Wait for applied AND no message.
	@echo "waiting for databaserole/forgejo to be applied with no error ..."; \
	for i in $$(seq 1 60); do \
		s=$$($(KUBECTL) -n db get databaserole forgejo -o jsonpath='{.status.applied}|{.status.message}'); \
		[ "$$s" = "true|" ] && { echo "databaserole/forgejo applied"; exit 0; }; \
		sleep 5; \
	done; \
	echo "databaserole/forgejo not applied: $$s" >&2; exit 1
	$(KUBECTL) -n db wait database/forgejo --for=jsonpath='{.status.applied}'=true --timeout=$(WAIT_TIMEOUT)

helm: prerequisites ## Install Forgejo with Helm (helm/values.yaml); waits for it, the HTTPRoute and the SSH LoadBalancer IP
	$(HELM) upgrade --install forgejo $(CHART) --version $(CHART_VERSION) \
		-n $(NAMESPACE) -f helm/values.yaml --wait --timeout 15m
	$(WAIT_READY) -n $(NAMESPACE)
	$(KUBECTL) -n $(NAMESPACE) wait httproute/forgejo \
		--for=jsonpath='{.status.parents[0].conditions[?(@.type=="Accepted")].status}'=True --timeout=$(WAIT_TIMEOUT)
	$(KUBECTL) -n $(NAMESPACE) wait service/forgejo-ssh \
		--for=jsonpath='{.status.loadBalancer.ingress[0].ip}'=192.168.3.201 --timeout=$(WAIT_TIMEOUT)

# Registration is idempotent: re-registering a secret updates the existing runner record.
runners: ## Register the runners' pre-shared secrets with Forgejo and deploy the runner StatefulSet; waits for it
	@for n in $(RUNNERS); do \
		t=$$($(call RUNNER_SECRET,token-$$n)); u=$$($(call RUNNER_SECRET,uuid-$$n)); \
		got=$$($(KUBECTL) -n $(NAMESPACE) exec deploy/forgejo -c forgejo -- \
			forgejo forgejo-cli actions register --name forgejo-runner-$$n --secret $$t 2>/dev/null | tail -1); \
		[ "$$got" = "$$u" ] || { echo "registering forgejo-runner-$$n failed (got '$$got', expected $$u)" >&2; exit 1; }; \
		echo "registered forgejo-runner-$$n ($$u)"; \
	done
	$(call kinstall,overlays/runners)

password: ## Print the initial Forgejo admin username and password, from their Secret (source: Bitwarden)
	@for k in username password; do $(KUBECTL) -n $(NAMESPACE) get secret forgejo-admin -o jsonpath="{.data.$$k}" | base64 -d; echo; done

# uninstall-helm keeps the data: the repository PVC (gitea-shared-storage, helm resource-policy
# keep), the forgejo namespace and its Secrets, and the "forgejo" database and role in cluster00
# (both reclaim policies: retain). See README.md "Uninstalling" to remove them for good.

uninstall-helm: ## Remove the runners and the Forgejo Helm release (keeps the PVC, Secrets and database)
	-$(call kdelete,overlays/runners)
	-$(HELM) uninstall forgejo -n $(NAMESPACE) --wait
