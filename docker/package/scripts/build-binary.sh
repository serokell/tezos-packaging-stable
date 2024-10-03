#!/usr/bin/env bash

# SPDX-FileCopyrightText: 2021 Oxhead Alpha
# SPDX-License-Identifier: LicenseRef-MIT-OA
set -euo pipefail

export OPAMYES=true
mkdir opamroot
export OPAMROOT=$PWD/opamroot

dune_filepath="$1"
binary_name="$2"

echo "******* Initializing opam-repository... *******"
opam init tezos ./opam-repository --bare --disable-sandboxing

echo "******* Entering tezos... *******"
cd tezos

echo "******* Creating switch *******"

touch ./scripts/version.sh

ocaml_version=""

. ./scripts/version.sh

opam switch create . --repositories=tezos "ocaml-base-compiler.$ocaml_version" --no-install

export OPAMSWITCH="$PWD"
opam repository remove default > /dev/null 2>&1

eval "$(opam env)"
OPAMASSUMEDEPEXTS=true opam install conf-rust conf-rust-2021

export CFLAGS="-fPIC ${CFLAGS:-}"
OPAMASSUMEDEPEXTS=true opam install opam/virtual/octez-deps.opam.locked --deps-only --criteria="-notuptodate,-changed,-removed"

dune build "$dune_filepath"
cp "./_build/default/$dune_filepath" "../$binary_name"
cd ..
