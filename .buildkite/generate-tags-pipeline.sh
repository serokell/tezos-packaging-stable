#! /usr/bin/env nix-shell
#! nix-shell shell.nix -i bash

# SPDX-FileCopyrightText: 2022 TQ Tezos <https://tqtezos.com/>
#
# SPDX-License-Identifier: LicenseRef-MIT-TQ

# This script generates part of the .buildkite/pipeline-for-tags.yml config file
# by appending every step associated with bottle building to the steps defined there.

set -euo pipefail

ymlappend () {
    echo "$1" >> .buildkite/pipeline-for-tags.yml
}

# we don't bottle meta-formulas that contain only services
formulae=("tezos-accuser-011-PtHangz2" "tezos-accuser-012-Psithaca" "tezos-admin-client" "tezos-baker-011-PtHangz2" "tezos-baker-012-Psithaca" "tezos-client" "tezos-codec" "tezos-endorser-011-PtHangz2" "tezos-node" "tezos-sandbox" "tezos-signer")
architecture=("arm64" "x86_64")
declare -A queues=( ["arm64"]="arm64-darwin" ["x86_64"]="x86_64-rosetta-darwin")

for arch in "${architecture[@]}"; do
  # tezos-sapling-params is used as a dependency for some of the formulas
  # so we handle it separately.
  # We don't build the bottle for it because it is never updated over time.
  queue="${queues[$arch]}"
  ymlappend "
 - label: Install tezos-sapling-params-$arch
   key: install-tsp-$arch
   agents:
     queue: \"$queue\"
   if: build.tag =~ /^v.*/
   commands:
   - brew install --formula ./Formula/tezos-sapling-params.rb"

  n=0
  for f in "${formulae[@]}"; do
    n=$((n+1))
    ymlappend "
 - label: Build $f bottle for Big Sur $arch
   key: build-bottle-$n-$arch
   agents:
     queue: \"$queue\"
   if: build.tag =~ /^v.*/
   commands:
   - ./scripts/build-one-bottle.sh \"$f\"
   artifact_paths:
     - '*.bottle.*'"
  done

  ymlappend "
 - label: Uninstall tezos-sapling-params $arch
   key: uninstall-tsp-$arch
   depends_on:"

  for ((i=1; i<=n; i++)); do
    ymlappend "   - build-bottle-$i-$arch"
  done

  ymlappend "   agents:
     queue: \"$queue\"
   if: build.tag =~ /^v.*/
   commands:
   - brew uninstall ./Formula/tezos-sapling-params.rb
 # To avoid running two brew processes together
 - wait"

done

ymlappend "
 - label: Add Big Sur bottle hashes to formulae
   depends_on:
   - \"uninstall-tsp-arm64\"
   - \"uninstall-tsp-x86_64\"
   if: build.tag =~ /^v.*/
   commands:
   - mkdir -p \"Big Sur \"
   - buildkite-agent artifact download \"*bottle.tar.gz\" \"Big Sur/\"
   - nix-shell ./scripts/shell.nix
       --run './scripts/sync-bottle-hashes.sh \"\$BUILDKITE_TAG\" \"Big Sur\"'
 - label: Attach bottles to the release
   depends_on:
   - \"uninstall-tsp\"
   if: build.tag =~ /^v.*/
   commands:
   - buildkite-agent artifact download \"*bottle.tar.gz\" .
   - nix-shell ./scripts/shell.nix
       --run 'gh release upload \"\$BUILDKITE_TAG\" *.bottle.*'"
