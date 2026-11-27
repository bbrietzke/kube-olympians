include ../common.mk

# MiroTalk C2C at https://video.brietzke.me (public, via the Cloudflare tunnel). See README.md.
# The Kubernetes objects are named "mirotalk", in the mirotalk namespace.
NAMESPACE := mirotalk
# API_KEY_SECRET, SESSION_SECRET and the Pocket ID client come from Bitwarden
# (base/external-secrets.yaml), so this needs external-secrets/ (helm + olympians) first.

.PHONY: olympians uninstall

olympians: ## Deploy MiroTalk C2C and its ExternalSecret (Bitwarden); needs traefik public + cloudflared + brietzke-auth; restarts it
	$(call kapply,overlays/olympians)
	$(KUBECTL) -n $(NAMESPACE) wait externalsecret/mirotalk-secrets --for=condition=Ready --timeout=$(WAIT_TIMEOUT)
	@# envFrom is read only at start, and ESO doesn't roll pods, so restart to pick up any change.
	$(KUBECTL) -n $(NAMESPACE) rollout restart deployment/mirotalk
	$(KUBECTL) -n $(NAMESPACE) rollout status deployment/mirotalk --timeout=$(WAIT_TIMEOUT)
	$(KUBECTL) -n $(NAMESPACE) wait httproute/mirotalk --for=jsonpath='{.status.parents[0].conditions[?(@.type=="Accepted")].status}'=True --timeout=$(WAIT_TIMEOUT)

uninstall: ## Remove MiroTalk and its namespace (no data is kept anywhere)
	-$(call kdelete,overlays/olympians)
