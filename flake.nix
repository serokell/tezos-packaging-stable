# SPDX-FileCopyrightText: 2022 Oxhead Alpha
# SPDX-License-Identifier: LicenseRef-MIT-OA

{
  description = "The tezos-packaging flake";

  nixConfig.flake-registry = "https://github.com/serokell/flake-registry/raw/master/flake-registry.json";

  inputs = {

    nixpkgs-unstable.url = "github:nixos/nixpkgs/nixos-unstable";
    # TODO: remove once https://github.com/serokell/nixpkgs/pull/61 is merged
    nixpkgs.url = "github:serokell/nixpkgs?rev=1dfdbb65d77430fc0935e8592d0abc4addcce711";

    nix.url = "github:nixos/nix";

    opam-nix.url = "github:tweag/opam-nix";

    flake-compat.flake = false;

    opam-repository.url = "gitlab:tezos/opam-repository";
    opam-repository.flake = false;

    tezos.url = "gitlab:tezos/tezos";
    tezos.flake = false;
  };

  outputs = inputs@{ self, nixpkgs, nixpkgs-unstable, flake-utils, serokell-nix, nix, ... }:
  let
    pkgs-darwin = nixpkgs-unstable.legacyPackages."aarch64-darwin";
    protocols = nixpkgs.lib.importJSON ./protocols.json;
    meta = nixpkgs.lib.importJSON ./meta.json;

    tezos = builtins.path {
      path = inputs.tezos;
      name = "tezos";
      # we exclude optional development packages
      filter = path: _: baseNameOf path != "octez-dev-deps.opam";
    };
    sources = { inherit tezos; inherit (inputs) opam-repository; };

    ocaml-overlay = import ./nix/build/ocaml-overlay.nix (inputs // { inherit sources protocols meta; });
  in pkgs-darwin.lib.recursiveUpdate
  {
      nixosModules = {
        tezos-node = import ./nix/modules/tezos-node.nix;
        tezos-accuser = import ./nix/modules/tezos-accuser.nix;
        tezos-baker = import ./nix/modules/tezos-baker.nix;
        tezos-signer = import ./nix/modules/tezos-signer.nix;
      };

      devShells."aarch64-darwin".autorelease-macos =
        import ./scripts/macos-shell.nix { pkgs = pkgs-darwin; };

      overlays.default = final: prev: nixpkgs.lib.composeManyExtensions [
        ocaml-overlay
        (final: prev: { inherit (inputs) serokell-nix; })
      ] final prev;
  } (flake-utils.lib.eachSystem [
      "x86_64-linux"
    ] (system:
    let

      overlay = final: prev: {
        inherit (inputs) serokell-nix;
        nix = nix.packages.${system}.default;
        zcash-params = callPackage ./nix/build/zcash.nix {};
      };

      pkgs = import nixpkgs {
        inherit system;
        overlays = [
          overlay
          serokell-nix.overlay
          ocaml-overlay
        ];
      };

      unstable = import nixpkgs-unstable {
        inherit system;
        overlays = [(_: _: { nix = nix.packages.${system}.default; })];
      };

      callPackage = pkg: input:
        import pkg (inputs // { inherit sources protocols meta pkgs; } // input);

      inherit (callPackage ./nix {}) octez-binaries tezos-binaries;

      release = callPackage ./release.nix {};

      # Remove this workaround once https://github.com/NixOS/nixpkgs/pull/160802 is merged upstream and present
      # in our nixpkgs fork
      qemu-aarch64-static = let
        qemu-aarch64-static-binary = pkgs.fetchurl {
          url = "https://github.com/multiarch/qemu-user-static/releases/download/v7.2.0-1/qemu-aarch64-static";
          sha256 = "0gw87p3x0b2b6a5w5bavgszhc06b77mafdd7g9f4h1dhqqnlprnw";
        };
      in pkgs.runCommand "qemu-aarch64-static" {} ''
        install -Dm777 ${qemu-aarch64-static-binary} $out/bin/qemu-aarch64-static
      '';

    in {

      legacyPackages = unstable;

      inherit release;

      packages = octez-binaries // tezos-binaries
        // { default = pkgs.linkFarmFromDrvs "binaries" (builtins.attrValues octez-binaries); };

      devShells = {
        buildkite = callPackage ./.buildkite/shell.nix {};
        autorelease = callPackage ./scripts/shell.nix {};
        docker-tezos-packages = callPackage ./shell.nix {};
        aarch64-build = pkgs.mkShell { buildInputs = [ qemu-aarch64-static pkgs.which pkgs.jq ]; };
      };

      checks = {
        tezos-nix-binaries = callPackage ./tests/tezos-nix-binaries.nix {};
        tezos-modules = callPackage ./tests/tezos-modules.nix {};
      };

      binaries-test = callPackage ./tests/tezos-binaries.nix {};
    }));
}
