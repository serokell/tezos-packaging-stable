#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2021 Oxhead Alpha
# SPDX-License-Identifier: LicenseRef-MIT-OA

# This script fetches the latest tag from the https://gitlab.com/tezos/tezos/ repository,
# compares it with the version presented in the nix/nix/sources.json, and performs an
# update if the versions are different

set -e

git fetch --all

# Get latest tag from tezos/tezos
git clone https://gitlab.com/tezos/tezos.git upstream-repo
cd upstream-repo
latest_upstream_tag_hash="$(git rev-list --tags --max-count=1)"
latest_upstream_tag="$(git describe --tags "$latest_upstream_tag_hash")"
opam_repository_tag='' # will be set by version.sh
git checkout "$latest_upstream_tag"
source scripts/version.sh
# copying metadata from octez repo
cp script-inputs/released-executables ../docker/octez-executables
cp script-inputs/dev-executables ../docker/dev-executables
cp script-inputs/active_protocol_versions_without_number ../docker/active-protocols
cd ..
rm -rf upstream-repo

branch_name="auto/$latest_upstream_tag-release"

our_tezos_tag="$(jq -r '.tezos_ref' meta.json | cut -d'/' -f3)"

new_meta=$(jq ".tezos_ref=\"$latest_upstream_tag\"" meta.json)
echo "$new_meta" > meta.json

if [[ "$latest_upstream_tag" = "$our_tezos_tag" ]]; then
  # If corresponding branch doesn't exist yet, then the release PR
  # wasn't created
  if true; then
    echo "Updating Tezos to $latest_upstream_tag"

    ./scripts/update-input.py tezos "$latest_upstream_tag_hash"
    ./scripts/update-input.py opam-repository "$opam_repository_tag"
    echo "buber" >> ./docker/octez-executables
    git commit -a -m "[Chore] Bump Tezos sources to $latest_upstream_tag"

    #./scripts/update-brew-formulae.sh "$latest_upstream_tag-1"
    #git commit -a -m "[Chore] Update brew formulae for $latest_upstream_tag"

    #sed -i 's/"release": "[0-9]\+"/"release": "1"/' ./meta.json
    ## Update version of tezos-baking package
    #sed -i "s/version = .*/version = \"$latest_upstream_tag\"/" ./baking/pyproject.toml
    ## Commit may fail when release number wasn't updated since the last release
    #git commit -a -m "[Chore] Reset release number for $latest_upstream_tag" || \
    #  echo "release number wasn't updated"

    #sed -i 's/letter_version *= *"[a-z]"/letter_version = ""/' ./docker/package/model.py
    ## Commit may fail when the letter version wasn't updated since the last release
    #git commit -a -m "[Chore] Reset letter_version for $latest_upstream_tag" || \
    #  echo "letter_version wasn't reset"

    #./scripts/update-release-binaries.py
    #git commit -a -m "[Chore] Update release binaries for $latest_upstream_tag"

    ##git push --set-upstream origin "$branch_name"

    #gh pr create -B master -t "[Chore] $latest_upstream_tag release" -F .github/release_pull_request_template.md
  fi
else
  echo "Our version is the same as the latest tag in the upstream repository"
fi
