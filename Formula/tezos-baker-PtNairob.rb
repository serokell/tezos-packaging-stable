# SPDX-FileCopyrightText: 2023 Oxhead Alpha
# SPDX-License-Identifier: LicenseRef-MIT-OA

class TezosBakerPtnairob < Formula
  @all_bins = []

  class << self
    attr_accessor :all_bins
  end
  homepage "https://gitlab.com/tezos/tezos"

  url "https://gitlab.com/tezos/tezos.git", :tag => "v17.3", :shallow => false

  version "v17.3-1"

  build_dependencies = %w[pkg-config coreutils autoconf rsync wget rustup-init cmake]
  build_dependencies.each do |dependency|
    depends_on dependency => :build
  end

  dependencies = %w[gmp hidapi libev libffi tezos-sapling-params]
  dependencies.each do |dependency|
    depends_on dependency
  end
  desc "Daemon for baking"

  bottle do
    root_url "https://github.com/serokell/tezos-packaging/releases/download/#{TezosBakerPtnairob.version}/"
    sha256 cellar: :any, monterey: "b0a2b5e165f14b15292f9dc2b8f1ddb3941f94dcce76ef91dd174b883e53674b"
  end

  def make_deps
    ENV.deparallelize
    ENV["CARGO_HOME"]="./.cargo"
    # Disable usage of instructions from the ADX extension to avoid incompatibility
    # with old CPUs, see https://gitlab.com/dannywillems/ocaml-bls12-381/-/merge_requests/135/
    ENV["BLST_PORTABLE"]="yes"
    # Here is the workaround to use opam 2.0.9 because Tezos is currently not compatible with opam 2.1.0 and newer
    arch = RUBY_PLATFORM.include?("arm64") ? "arm64" : "x86_64"
    system "curl", "-L", "https://github.com/ocaml/opam/releases/download/2.0.9/opam-2.0.9-#{arch}-macos", "--create-dirs", "-o", "#{ENV["HOME"]}/.opam-bin/opam"
    system "chmod", "+x", "#{ENV["HOME"]}/.opam-bin/opam"
    ENV["PATH"]="#{ENV["HOME"]}/.opam-bin:#{ENV["PATH"]}"
    system "rustup-init", "--default-toolchain", "1.60.0", "-y"
    system "opam", "init", "--bare", "--debug", "--auto-setup", "--disable-sandboxing"
    system ["source .cargo/env",  "make build-deps"].join(" && ")
  end

  def install_template(dune_path, exec_path, name)
    bin.mkpath
    self.class.all_bins << name
    system ["eval $(opam env)", "dune build #{dune_path}", "cp #{exec_path} #{name}"].join(" && ")
    bin.install name
    ln_sf "#{bin}/#{name}", "#{bin}/#{name.gsub("octez", "tezos")}"
  end

  def install
    startup_contents =
      <<~EOS
      #!/usr/bin/env bash

      set -euo pipefail

      baker="#{bin}/octez-baker-PtNairob"

      baker_config="$TEZOS_CLIENT_DIR/config"
      mkdir -p "$TEZOS_CLIENT_DIR"

      if [ ! -f "$baker_config" ]; then
          "$baker" --endpoint "$NODE_RPC_SCHEME://$NODE_RPC_ADDR" \
                  config init --output "$baker_config" >/dev/null 2>&1
      else
          "$baker" --endpoint "$NODE_RPC_SCHEME://$NODE_RPC_ADDR" \
                  config update >/dev/null 2>&1
      fi

      launch_baker() {
          exec "$baker" \
              --endpoint "$NODE_RPC_SCHEME://$NODE_RPC_ADDR" \
              run with local node "$TEZOS_NODE_DIR" "$@"
      }

      if [[ -z "$BAKER_ACCOUNT" ]]; then
          launch_baker
      else
          launch_baker "$BAKER_ACCOUNT"
      fi
    EOS
    File.write("tezos-baker-PtNairob-start", startup_contents)
    bin.install "tezos-baker-PtNairob-start"
    make_deps
    install_template "src/proto_017_PtNairob/bin_baker/main_baker_017_PtNairob.exe",
                     "_build/default/src/proto_017_PtNairob/bin_baker/main_baker_017_PtNairob.exe",
                     "octez-baker-PtNairob"
  end

  service do
    run opt_bin/"tezos-baker-PtNairob-start"
    require_root true
    environment_variables TEZOS_CLIENT_DIR: var/"lib/tezos/client", TEZOS_NODE_DIR: "", NODE_RPC_SCHEME: "http", NODE_RPC_ADDR: "localhost:8732", BAKER_ACCOUNT: ""
    keep_alive true
    log_path var/"log/tezos-baker-PtNairob.log"
    error_log_path var/"log/tezos-baker-PtNairob.log"
  end

  def post_install
    mkdir "#{var}/lib/tezos/client"
  end
end
