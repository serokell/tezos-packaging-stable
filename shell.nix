# SPDX-FileCopyrightText: 2022 Oxhead Alpha
# SPDX-License-Identifier: LicenseRef-MIT-OA

{ pkgs, legacyPkgs, meta, ...  }:
let
  legacyInputs = with legacyPkgs; [
    rpm
    dput
    copr-cli
    debian-devscripts
  ];
  pythonPkgs = with pkgs; [
    nodePackages_latest.pyright
    (python39.withPackages (ps: [
      ps.pip
      ps.build
      ps.black
    ]))
  ];
in
with pkgs; mkShell {
  buildInputs = [
    gh
    jq
    git
    perl
    which
    gnupg
    rename
    gnused
    coreutils
    moreutils
    util-linux
    shellcheck
    buildkite-agent
  ] ++ legacyInputs ++ pythonPkgs;
  OCTEZ_VERSION= with pkgs.lib; lists.last (strings.splitString "/" (meta.tezos_ref));
  DOCKER_BUILDKIT = 1;
}
