include ../common.mk

NAMESPACE  := cloudflared
# The tunnel token comes from Bitwarden (base/external-secret.yaml), so this needs
# external-secrets/ (helm + olympians) first.

.PHONY: olympians whoami uninstall uninstall-whoami

olympians: ## Deploy the cloudflared connector and its token ExternalSecret (Bitwarden); needs traefik postCertManager
	$(call kapply,overlays/olympians)
	$(KUBECTL) -n $(NAMESPACE) wait externalsecret/cloudflared-tunnel-token --for=condition=Ready --timeout=$(WAIT_TIMEOUT)
	$(KUSTOMIZE) build overlays/olympians | $(WAIT_READY)

whoami: ## Deploy the whoami test app on both Gateways (whoami.brietzke.me + whoami.faultycloud.xyz)
	$(call kinstall,overlays/whoami)
	$(KUBECTL) -n whoami wait httproute/whoami --for=jsonpath='{.status.parents[1].conditions[?(@.type=="Accepted")].status}'=True --timeout=$(WAIT_TIMEOUT)

uninstall-whoami: ## Remove the whoami test app and its namespace
	-$(call kdelete,overlays/whoami)

uninstall: uninstall-whoami ## Remove the connector, its token Secret and namespace (the tunnel stays in Cloudflare)
	-$(call kdelete,overlays/olympians)
