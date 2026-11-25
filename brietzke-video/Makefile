include ../common.mk

# MiroTalk C2C at https://video.brietzke.me (public, via the Cloudflare tunnel). See README.md.
# The Kubernetes objects are named "mirotalk", in the mirotalk namespace.
NAMESPACE := mirotalk
ENV_FILE  := base/mirotalk.env

.PHONY: prerequisites olympians uninstall

random = $$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c $(1))

# mirotalk.env holds API_KEY_SECRET and SESSION_SECRET (generated here, once) and the OIDC client
# from Pocket ID (OIDC_CLIENT_ID / OIDC_CLIENT_SECRET, pasted in by hand; see README.md).
prerequisites: ## Generate base/mirotalk.env secrets if missing; refuse until the OIDC client is filled in
	@test -f $(ENV_FILE) || { touch $(ENV_FILE); chmod 600 $(ENV_FILE); }
	@grep -q '^API_KEY_SECRET=' $(ENV_FILE) || { echo "API_KEY_SECRET=$(call random,40)" >> $(ENV_FILE); echo "added API_KEY_SECRET"; }
	@grep -q '^SESSION_SECRET=' $(ENV_FILE) || { echo "SESSION_SECRET=$(call random,48)" >> $(ENV_FILE); echo "added SESSION_SECRET"; }
	@grep -q '^OIDC_CLIENT_ID=' $(ENV_FILE) || { printf 'OIDC_CLIENT_ID=REPLACE_ME\nOIDC_CLIENT_SECRET=REPLACE_ME\n' >> $(ENV_FILE); echo "added OIDC_CLIENT_ID / OIDC_CLIENT_SECRET placeholders"; }
	@! grep -q REPLACE_ME $(ENV_FILE) || { echo "fill in the Pocket ID client (OIDC_CLIENT_ID / OIDC_CLIENT_SECRET) in $(ENV_FILE); see README.md" >&2; exit 1; }

olympians: prerequisites ## Deploy MiroTalk C2C (needs traefik public + cloudflared + brietzke-auth); restarts it on config changes
	$(call kapply,overlays/olympians)
	@# envFrom is read only at start, so roll the pod whenever the ConfigMap or Secret changes.
	$(KUBECTL) -n $(NAMESPACE) rollout restart deployment/mirotalk
	$(KUBECTL) -n $(NAMESPACE) rollout status deployment/mirotalk --timeout=$(WAIT_TIMEOUT)
	$(KUBECTL) -n $(NAMESPACE) wait httproute/mirotalk --for=jsonpath='{.status.parents[0].conditions[?(@.type=="Accepted")].status}'=True --timeout=$(WAIT_TIMEOUT)

uninstall: ## Remove MiroTalk and its namespace (no data is kept anywhere)
	-$(call kdelete,overlays/olympians)
