# SPDX-FileCopyrightText: 2021 TQ Tezos <https://tqtezos.com/>
#
# SPDX-License-Identifier: LicenseRef-MIT-TQ
let
  native_packaging_changes_regexes = [
    "docker\/package/\.*"
    "docker\/docker-tezos-packages\.sh"
    "meta\.json"
    "protocols\.json"
    "nix\/nix\/sources\.json"
  ];
  static_binaries_changes_regexes = [
    "docker\/build/\.*"
    "docker\/docker-static-build\.sh"
    "nix\/nix\/sources\.json"
    "meta\.json"
    "protocols\.json"
  ];
  nix_changes_regexes = [
    ".*\.nix"
    "protocols\.json"
  ];
  brew_changes_regexes = [
    "Formula\/.*\.rb"
  ];
in
{
  env = {
    SET_VERSION = "export TEZOS_VERSION=\"$(cat nix/nix/sources.json | jq -r '.tezos.ref' | cut -d'/' -f3)\"";
  };
  steps = [
    { label = "reuse lint";
      command= "nix run -f . pkgs.reuse -c reuse lint";
    }
    { label = "check trailing whitespace";
      command= ".buildkite/check-trailing-whitespace.sh";
    }
    { label = "crossref-verify";
      command = "nix run -f https://github.com/serokell/crossref-verifier/archive/68a1f9d25b6e7835fea8299b18a3e6c61dbb2a5c.tar.gz -c crossref-verify";
      soft_fail = true;
    }
    { label = "build via nix";
      command = "nix-build ./nix -A binaries -o binaries";
      branches = "!master";
      only_changes = nix_changes_regexes;
    }
    { label = "test nix-built binaries";
      command = "nix-build tests/tezos-nix-binaries.nix --no-out-link";
      only_changes = nix_changes_regexes;
    }
    { label = "build via docker";
      commands = [
        "eval \"$SET_VERSION\""
        "cd docker"
        "./docker-static-build.sh"
        "nix run -f.. pkgs.upx -c upx tezos-*"
      ];
      artifact_paths = [
        "./docker/tezos-*"
      ];
      agents = { queue = "docker"; };
      only_changes = static_binaries_changes_regexes;
    }
    { label = "build arm via docker";
      commands = [
        "eval \"$SET_VERSION\""
        "cd docker"
        "./docker-static-build.sh"
        "upx tezos-*"
        "for f in ./tezos-*; do mv mv \"\$f\" \"\$f-arm64\"; done"
      ];
      artifact_paths = [
        "./docker/tezos-*"
      ];
      agents = { queue = "arm64-build"; };
      only_changes = static_binaries_changes_regexes;
    }
    { label = "check brew formulas";
      commands = [
        # Check all formulas except 'tezos.rb' because it's a base class for all other formulas
        "find ./Formula -type f -name \"*.rb\" -exec ruby -c {} +"
        # All formulas share the same source URL inherited by the Tezos class, so it's fine
        # to fetch sources for only one formula
        "brew fetch -s ./Formula/tezos-client.rb"
      ];
      agents = { queue = "x86_64-darwin"; };
      only_changes = brew_changes_regexes;
    }
    "wait"
    { label = "test docker-built binaries";
      commands = [
        "buildkite-agent artifact download \"docker/*\" . --step \"build via docker\""
        "chmod +x ./docker/*"
        "nix-build tests/tezos-binaries.nix --no-out-link --arg path-to-binaries ./docker"
      ];
      branches = "!master";
      only_changes = static_binaries_changes_regexes;
    }
    { label = "test deb source packages via docker";
      commands = [
        "eval \"$SET_VERSION\""
        "./docker/docker-tezos-packages.sh --os ubuntu --type source"
      ];
      artifact_paths = [
        "./out/*"
      ];
      branches = "!master";
      timeout_in_minutes = 60;
      agents = { queue = "docker"; };
      only_changes = native_packaging_changes_regexes;
    }
    { label = "test deb binary packages via docker";
      commands = [
        "eval \"$SET_VERSION\""
        # Building all binary packages will take significant amount of time, so we build only one
        # in order to ensure package generation sanity
        "./docker/docker-tezos-packages.sh --os ubuntu --type binary --package tezos-baker-008-PtEdo2Zk"
        "rm -rf out"
      ];
      artifact_paths = [
        "./out/*"
      ];
      # It takes much time to build binary package, so we do it only on master
      branches = "master";
      timeout_in_minutes = 90;
      agents = { queue = "docker"; };
      only_changes = native_packaging_changes_regexes;
    }
    { label = "test rpm source packages via docker";
      commands = [
        "eval \"$SET_VERSION\""
        "./docker/docker-tezos-packages.sh --os fedora --type source"
      ];
      artifact_paths = [
        "./out/*"
      ];
      branches = "!master";
      timeout_in_minutes = 60;
      agents = { queue = "docker"; };
      only_changes = native_packaging_changes_regexes;
    }
    { label = "test r binary packages via docker";
      commands = [
        "eval \"$SET_VERSION\""
        # Building all binary packages will take significant amount of time, so we build only one
        # in order to ensure package generation sanity
        "./docker/docker-tezos-packages.sh --os fedora --type binary --package tezos-baker-008-PtEdo2Zk"
        "rm -rf out"
      ];
      artifact_paths = [
        "./out/*"
      ];
      # It takes much time to build binary package, so we do it only on master
      branches = "master";
      timeout_in_minutes = 90;
      agents = { queue = "docker"; };
      only_changes = native_packaging_changes_regexes;
    }
    "wait"
    { label = "create auto pre-release";
      commands = [
        "mkdir binaries"
        "mkdir arm-binaries"
        "buildkite-agent artifact download \"docker/*\" binaries --step \"build via docker\""
        "buildkite-agent artifact download \"docker/*\" arm-binaries --step \"build arm via docker\""
        "./scripts/autorelease.sh"
      ];
      branches = "master";
      only_changes = static_binaries_changes_regexes ++ brew_changes_regexes;
    }
  ];
}
