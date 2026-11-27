include ../common.mk

NAMESPACE     := cert-manager
CHART_REPO    := https://charts.jetstack.io
CHART_VERSION := v1.21.3
ISSUER        := letsencrypt-dns01

# The Cloudflare token comes from Bitwarden (ExternalSecret in base/), so `olympians` needs
# external-secrets/ (helm + olympians) first. external-secrets itself only needs cert-manager
# installed, not this issuer, so there is no loop.

# Wait for the cert-manager workloads, then until the webhook accepts the issuer.
define wait_certmanager
$(WAIT_READY) -n $(NAMESPACE)
$(call wait_accepts,cat base/issuers.yaml)
endef

.PHONY: prerequisites install helm olympians uninstall uninstall-helm

prerequisites: ## Install the Gateway API CRDs (cert-manager runs with Gateway API support on)
	$(MAKE) -C ../traefik prerequisites

install: prerequisites ## Install cert-manager from the upstream manifest via kustomize; waits for its webhook
	$(call kinstall,overlays/install)
	$(wait_certmanager)

helm: prerequisites ## Install cert-manager with Helm (helm/values.yaml); waits for its webhook
	$(HELM) upgrade --install cert-manager cert-manager --repo $(CHART_REPO) --version $(CHART_VERSION) \
		-n $(NAMESPACE) --create-namespace -f helm/values.yaml --wait
	$(wait_certmanager)

olympians: ## Apply the Cloudflare token ExternalSecret (Bitwarden) and the letsencrypt-dns01 ClusterIssuer; waits until both are Ready
	$(call wait_accepts,$(KUSTOMIZE) build overlays/olympians)
	$(call kapply,overlays/olympians)
	$(KUBECTL) -n $(NAMESPACE) wait externalsecret/cloudflare-api-token-secret --for=condition=Ready --timeout=$(WAIT_TIMEOUT)
	$(KUBECTL) wait clusterissuer/$(ISSUER) --for=condition=Ready --timeout=$(WAIT_TIMEOUT)

# Neither uninstall touches the Gateway API CRDs; `make -C ../traefik uninstall` owns those.

uninstall: ## Remove the issuer, token Secret and the kustomize install (deletes all cert-manager CRDs and Certificates)
	-$(call kdelete,overlays/olympians)
	-$(call kdelete,overlays/install)

uninstall-helm: ## Remove the issuer, token Secret and the Helm release (the chart keeps its CRDs)
	-$(call kdelete,overlays/olympians)
	-$(HELM) uninstall cert-manager -n $(NAMESPACE) --wait
	-$(KUBECTL) delete namespace $(NAMESPACE) --ignore-not-found
