include ../common.mk

# MiroTalk C2C at https://video.brietzke.me (public, via the Cloudflare tunnel). See README.md.
# The Kubernetes objects are named "mirotalk", in the mirotalk namespace.
NAMESPACE := mirotalk
ENV_FILE  := base/mirotalk.env

.PHONY: prerequisites olympians uninstall

prerequisites: ## Generate base/mirotalk.env (API_KEY_SECRET) if missing
	@test -f $(ENV_FILE) || { printf 'API_KEY_SECRET=%s\n' "$$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 40)" > $(ENV_FILE); \
		chmod 600 $(ENV_FILE); echo "generated $(ENV_FILE)"; }
	@! grep -q REPLACE_ME $(ENV_FILE) || { echo "replace REPLACE_ME in $(ENV_FILE)" >&2; exit 1; }

olympians: prerequisites ## Deploy MiroTalk C2C (needs traefik public + cloudflared); restarts it on config changes
	$(call kapply,overlays/olympians)
	@# envFrom is read only at start, so roll the pod whenever the ConfigMap or Secret changes.
	$(KUBECTL) -n $(NAMESPACE) rollout restart deployment/mirotalk
	$(KUBECTL) -n $(NAMESPACE) rollout status deployment/mirotalk --timeout=$(WAIT_TIMEOUT)
	$(KUBECTL) -n $(NAMESPACE) wait httproute/mirotalk --for=jsonpath='{.status.parents[0].conditions[?(@.type=="Accepted")].status}'=True --timeout=$(WAIT_TIMEOUT)

uninstall: ## Remove MiroTalk and its namespace (no data is kept anywhere)
	-$(call kdelete,overlays/olympians)
