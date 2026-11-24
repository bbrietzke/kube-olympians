include ../common.mk

# brietzke.me: the Hugo site built from the brietzke-me/website Forgejo repo. The objects in the
# brietzke-me namespace are named "website".

NAMESPACE := brietzke-me
IMAGE     := harbor.faultycloud.xyz/library/brietzke-me
OVERLAY   := overlays/olympians

.PHONY: deploy olympians uninstall

deploy: ## Set the site image to TAG (a commit's sha12 from the build job) and apply
	@test -n "$(TAG)" || { echo "usage: make deploy TAG=<sha12>  (printed by the Forgejo build job)" >&2; exit 1; }
	cd $(OVERLAY) && $(KUSTOMIZE) edit set image $(IMAGE)=$(IMAGE):$(TAG)
	$(MAKE) olympians

olympians: ## Apply the site at the tag in overlays/olympians (needs traefik public + cloudflared)
	@! grep -q 'newTag: REPLACE_ME' $(OVERLAY)/kustomization.yaml || { \
		echo "no image tag yet: run make deploy TAG=<sha12> after the first Forgejo build" >&2; exit 1; }
	$(call kinstall,$(OVERLAY))
	$(KUBECTL) -n $(NAMESPACE) wait httproute/website --for=jsonpath='{.status.parents[0].conditions[?(@.type=="Accepted")].status}'=True --timeout=$(WAIT_TIMEOUT)

uninstall: ## Remove the site and its namespace
	-$(call kdelete,$(OVERLAY))
