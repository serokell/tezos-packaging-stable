#!/usr/bin/env bash
# shellcheck shell=bash
# SPDX-FileCopyrightText: 2021 Oxhead Alpha
# SPDX-License-Identifier: LicenseRef-MIT-OA

# This script takes the Buildkite build message, usually the last commit's title.

set -euo pipefail

# Project name, inferred from repository name
project=$(basename "$(pwd)")

# The directory in which artifacts will be created
TEMPDIR=$(mktemp -d)
function finish {
  rm -rf "$TEMPDIR"
}
trap finish EXIT

assets_dir=$TEMPDIR/assets

# Build tezos-release
nix-build . -A release -o "$TEMPDIR"/"$project" \
          --arg docker-binaries ./binaries/docker --arg docker-arm-binaries ./arm-binaries/docker
mkdir -p "$assets_dir"
# Move archive with binaries and tezos license to assets
shopt -s extglob
cp -L "$TEMPDIR"/"$project"/!(*.md) "$assets_dir"
# Iterate over assets, calculate sha256sum and sign them in order
# to include this additional info to the release assets as well
for asset in "$assets_dir"/*; do
    sha256sum "$asset" | sed 's/ .*/ /' > "$asset.sha256"
    gpg --armor --detach-sign "$asset"
done

mode_flag=""

tag="octez-v20.0-1"

# Update the tag
git fetch # So that the script can be run from an arbitrary checkout
git tag -f "$tag"
git push origin "$tag" --force

# Create release
# Note: "mode_flag" should not be quoted here because an empty value results in
# two consecutive spaces, which gh will interpret incorrectly as an empty param
# shellcheck disable=SC2086
gh release create "$tag" --title "$tag" $mode_flag -F "$TEMPDIR"/"$project"/release-notes.md

# Upload assets
gh release upload "$tag" "$assets_dir"/*
