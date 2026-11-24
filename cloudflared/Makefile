include ../common.mk

NAMESPACE  := cloudflared
TOKEN_FILE := base/cloudflared.env

.PHONY: olympians whoami uninstall uninstall-whoami

olympians: ## Deploy the cloudflared connector (needs base/cloudflared.env and traefik postCertManager)
	@grep -Eq '^TUNNEL_TOKEN=.+' $(TOKEN_FILE) 2>/dev/null && ! grep -q 'REPLACE_ME' $(TOKEN_FILE) || { \
		echo "$(TOKEN_FILE) is missing or has no token: cp $(TOKEN_FILE).example $(TOKEN_FILE) and fill in TUNNEL_TOKEN." >&2; \
		exit 1; }
	$(call kinstall,overlays/olympians)

whoami: ## Deploy the whoami test app on both Gateways (whoami.brietzke.me + whoami.faultycloud.xyz)
	$(call kinstall,overlays/whoami)
	$(KUBECTL) -n whoami wait httproute/whoami --for=jsonpath='{.status.parents[1].conditions[?(@.type=="Accepted")].status}'=True --timeout=$(WAIT_TIMEOUT)

uninstall-whoami: ## Remove the whoami test app and its namespace
	-$(call kdelete,overlays/whoami)

uninstall: uninstall-whoami ## Remove the connector, its token Secret and namespace (the tunnel stays in Cloudflare)
	-$(call kdelete,overlays/olympians)
