#!/usr/bin/env bash

# SPDX-FileCopyrightText: 2021 Oxhead Alpha
# SPDX-License-Identifier: LicenseRef-MIT-OA
set -euo pipefail

dune_filepath="$1"
binary_name="$2"

cd tezos
eval "$(opam env)"
dune build "$dune_filepath"
cp "./_build/default/$dune_filepath" "../$binary_name"
cd ..
