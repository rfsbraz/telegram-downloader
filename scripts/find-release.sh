#!/usr/bin/env bash
# Decide whether the push to main that started this run is a release sync.
# Prints tag=... and version=... (to GITHUB_OUTPUT when set). Needs a checkout with full history and tags.
set -euo pipefail
sha=${GITHUB_SHA:?}
glob=${TAG_GLOB:?}            # 'v*' or 'gentle-owl-v*' or 'rebo-v*'
out=${GITHUB_OUTPUT:-/dev/stdout}
if ! second=$(git rev-parse -q --verify "$sha^2"); then
  echo "release=false" >> "$out"; echo "not a merge commit, no release"; exit 0
fi
tag=$(git tag --points-at "$second" --list "$glob" | sort -V | tail -n1)
if [ -z "$tag" ]; then
  echo "release=false" >> "$out"; echo "merged commit carries no release tag, no release"; exit 0
fi
version=$(git show "$sha:.release-please-manifest.json" | jq -r '."."')
if [ "${tag##*v}" != "$version" ]; then
  echo "tag $tag does not match manifest $version on main" >&2; exit 1
fi
{ echo "release=true"; echo "tag=$tag"; echo "version=$version"; } >> "$out"
