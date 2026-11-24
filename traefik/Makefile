include ../common.mk

NAMESPACE     := traefik
CHART_REPO    := https://traefik.github.io/charts
CHART_VERSION := 42.4.1
# The install overlay inflates the chart and reads ../../helm/install.yaml.
HELM_BUILD    := $(KUSTOMIZE) build --enable-helm --load-restrictor LoadRestrictionsNone overlays/install

# Wait for every Traefik workload and for the Gateway to be Programmed (address assigned).
define wait_traefik
$(WAIT_READY) -n $(NAMESPACE)
$(KUBECTL) -n $(NAMESPACE) wait gateway --all --for=condition=Programmed --timeout=$(WAIT_TIMEOUT)
endef

.PHONY: prerequisites gateway install helm postCertManager public uninstall-public uninstall uninstall-helm

prerequisites: ## Install the Gateway API v1.7.0 standard CRDs
	$(call kinstall,overlays/prerequisites)

gateway: prerequisites ## Alias for prerequisites

install: prerequisites ## Install Traefik via kustomize (chart inflated with helm/install.yaml)
	$(HELM_BUILD) | $(KUBECTL) apply --server-side --force-conflicts -f -
	$(HELM_BUILD) | $(WAIT_READY)
	$(KUBECTL) -n $(NAMESPACE) wait gateway --all --for=condition=Programmed --timeout=$(WAIT_TIMEOUT)

helm: prerequisites ## Install Traefik with Helm (helm/install.yaml)
	$(HELM) upgrade --install traefik traefik --repo $(CHART_REPO) --version $(CHART_VERSION) \
		-n $(NAMESPACE) --create-namespace -f helm/install.yaml --wait
	$(wait_traefik)

postCertManager: prerequisites ## Upgrade the Helm release to the HTTPS gateway (needs cert-manager + letsencrypt-dns01)
	$(HELM) upgrade --install traefik traefik --repo $(CHART_REPO) --version $(CHART_VERSION) \
		-n $(NAMESPACE) --create-namespace -f helm/postCertManager.yaml --wait
	$(wait_traefik)
	$(MAKE) public

public: ## Apply the traefik-public Gateway (brietzke.me, tunnel only); run by postCertManager
	$(call kapply,overlays/public)
	$(KUBECTL) -n $(NAMESPACE) wait gateway/traefik-public --for=condition=Programmed --timeout=$(WAIT_TIMEOUT)

uninstall-public: ## Remove the traefik-public Gateway (routes attached to it stop being served)
	-$(call kdelete,overlays/public)

# Both uninstall targets also remove the Gateway API CRDs, which deletes every
# Gateway/HTTPRoute in the cluster.

uninstall: ## Remove the kustomize install and the Gateway API CRDs
	-$(HELM_BUILD) | $(KUBECTL) delete --ignore-not-found -f -
	-$(call kdelete,overlays/prerequisites)

uninstall-helm: ## Remove the Helm release and the Gateway API CRDs
	-$(HELM) uninstall traefik -n $(NAMESPACE) --wait
	-$(KUBECTL) delete namespace $(NAMESPACE) --ignore-not-found
	-$(call kdelete,overlays/prerequisites)
