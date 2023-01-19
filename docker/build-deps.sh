#!/usr/bin/env bash

# SPDX-FileCopyrightText: 2023 Oxhead Alpha
# SPDX-License-Identifier: LicenseRef-MIT-OA
set -euo pipefail

cd tezos
opam init local ../opam-repository --bare --disable-sandboxing
opam switch create . --repositories=local --no-install
eval "$(opam env)"
opams=()
while IFS=  read -r -d $'\0'; do
    # we exclude optional development packages
    if [ "$REPLY" != "./opam/virtual/octez-dev-deps.opam" ]; then
        opams+=("$REPLY")
    fi
done < <(find ./vendors ./src ./tezt ./opam -name \*.opam -print0)
export CFLAGS="-fPIC ${CFLAGS:-}"
opam install "${opams[@]}" --deps-only --criteria="-notuptodate,-changed,-removed"
