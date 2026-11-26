include ../common.mk

# cost-center labels for chargeback (OpenCost dashboards in opencost/). See README.md.
FIELD_MANAGER := cost-centers

.PHONY: olympians labels policy check

olympians: labels policy ## Label the unowned namespaces and install the warn-only label policy

labels: ## Label the namespaces nothing in this repo creates (base/namespaces.yaml), owning only that label
	$(KUBECTL) apply --server-side --field-manager=$(FIELD_MANAGER) -f base/namespaces.yaml

policy: ## Install the allowed values (ConfigMap) and the Warn + Audit admission policy for namespaces
	$(call kapply,policy)

check: ## List every namespace with its cost-center; exits non-zero if any is missing one
	@$(KUBECTL) get namespaces -L cost-center --no-headers | awk '{ printf "%-22s %s\n", $$1, ($$4 == "" ? "MISSING" : $$4) }'
	@! $(KUBECTL) get namespaces -L cost-center --no-headers | awk '$$4 == "" { found = 1 } END { exit !found }' || { echo "some namespaces have no cost-center label" >&2; exit 1; }
