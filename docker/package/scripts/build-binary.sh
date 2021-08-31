#!/usr/bin/env bash

# SPDX-FileCopyrightText: 2021 TQ Tezos <https://tqtezos.com/>
#
# SPDX-License-Identifier: LicenseRef-MIT-TQ
set -euo pipefail

export OPAMYES=true
mkdir opamroot
export OPAMROOT=$PWD/opamroot

dune_filepath="$1"
binary_name="$2"

cd tezos
opam init local ../opam-repository --bare --disable-sandboxing
opam switch create . --repositories=local
eval "$(opam env)"
opams="$(find ./vendors ./src -name \*.opam -print)"
opam install $opams --deps-only --criteria="-notuptodate,-changed,-removed"
eval "$(opam env)"
dune build "$dune_filepath"
cp "./_build/default/$dune_filepath" "../$binary_name"
cd ..