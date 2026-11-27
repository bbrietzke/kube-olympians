include ../common.mk

# External Secrets Operator + Bitwarden Secrets Manager (US cloud): Kubernetes Secrets come from the
# "olympians" Bitwarden project instead of git-ignored .env files. Helm only. See README.md.
# Needs certificateManager (the SDK server's TLS certificate) and nothing else.
NAMESPACE     := external-secrets
CHART_REPO    := https://charts.external-secrets.io
CHART_VERSION := 2.15.0
TOKEN_ENV     := base/bitwarden.env

.PHONY: prerequisites helm olympians rescue rescue-done uninstall-helm

prerequisites: ## Apply the namespace and the SDK server's TLS certificate (cert-manager); waits for it
	$(call kapply,overlays/prerequisites)
	$(KUBECTL) -n $(NAMESPACE) wait certificate --all --for=condition=Ready --timeout=$(WAIT_TIMEOUT)

helm: prerequisites ## Install or upgrade ESO and the bitwarden-sdk-server (helm/values.yaml)
	$(HELM) upgrade --install external-secrets external-secrets --repo $(CHART_REPO) --version $(CHART_VERSION) \
		-n $(NAMESPACE) -f helm/values.yaml --wait --timeout 10m
	$(WAIT_READY) -n $(NAMESPACE)

olympians: ## Apply the machine account token (base/bitwarden.env) and the "bitwarden" ClusterSecretStore; waits for it
	@test -f $(TOKEN_ENV) || { cp $(TOKEN_ENV).example $(TOKEN_ENV); chmod 600 $(TOKEN_ENV); }
	@! grep -q REPLACE_ME $(TOKEN_ENV) || { echo "put the Bitwarden machine account token in $(TOKEN_ENV); see README.md" >&2; exit 1; }
	$(call kapply,overlays/olympians)
	$(KUBECTL) wait clustersecretstore/bitwarden --for=condition=Ready --timeout=$(WAIT_TIMEOUT)

rescue: ## Copy the cluster-only Secrets (no .env file left) into Bitwarden with PushSecrets; waits until synced
	$(call kapply,overlays/rescue)
	$(KUBECTL) wait pushsecret --all-namespaces -l olympians/secrets-rescue=true --for=condition=Ready --timeout=$(WAIT_TIMEOUT)

rescue-done: ## Delete the rescue PushSecrets (the Bitwarden copies stay: deletionPolicy None)
	-$(call kdelete,overlays/rescue)

uninstall-helm: ## Remove ESO (synced Secrets stay as they are; the CRDs go with the chart)
	-$(call kdelete,overlays/olympians)
	-$(HELM) uninstall external-secrets -n $(NAMESPACE) --wait
