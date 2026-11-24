#!/usr/bin/env bash
# Wait until applied resources are ready, so make targets can be chained safely.
#
#   <manifests on stdin> | wait-ready.sh        wait for the objects in the manifests
#   wait-ready.sh -n <namespace>                wait for every workload in a namespace
#
# Ready means: CRDs Established, Deployments / DaemonSets / StatefulSets fully rolled out.
# Other kinds are ignored. Written for macOS bash 3.2.
set -euo pipefail

KUBECTL=${KUBECTL:-kubectl}
TIMEOUT=${WAIT_TIMEOUT:-300s}

if [ "${1:-}" = "-n" ]; then
  ns=${2:?namespace required}
  objs=$($KUBECTL -n "$ns" get deployments,daemonsets,statefulsets --no-headers \
    -o custom-columns=K:.kind,NS:.metadata.namespace,N:.metadata.name)
else
  manifests=$(cat)
  [ -n "$manifests" ] || exit 0
  objs=$(printf '%s\n' "$manifests" | $KUBECTL get -f - --no-headers \
    -o custom-columns=K:.kind,NS:.metadata.namespace,N:.metadata.name)
fi

[ -n "$objs" ] || exit 0

while read -r kind ns name; do
  [ -n "$kind" ] || continue
  case "$kind" in
    CustomResourceDefinition)
      $KUBECTL wait --for=condition=Established --timeout="$TIMEOUT" "crd/$name"
      ;;
    Deployment|DaemonSet|StatefulSet)
      res=$(printf '%s' "$kind" | tr '[:upper:]' '[:lower:]')
      $KUBECTL -n "$ns" rollout status "$res/$name" --timeout="$TIMEOUT"
      ;;
  esac
done <<EOF
$objs
EOF
