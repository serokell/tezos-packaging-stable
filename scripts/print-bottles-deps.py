import subprocess
import sys

binaries = [
    # "tezos-client",
    # "tezos-admin-client",
    # "tezos-node",
    # "tezos-signer",
    # "tezos-codec",
    # "tezos-baker-PtMumbai",
    # "tezos-accuser-PtMumbai",
    # "tezos-smart-rollup-client-PtMumbai",
    # "tezos-smart-rollup-node-PtMumbai",
    # "tezos-baker-PtNairob",
    # "tezos-accuser-PtNairob",
    # "tezos-smart-rollup-client-PtNairob",
    # "tezos-smart-rollup-node-PtNairob",
    "tezos-dac-client",
    "tezos-dac-node"
]


def install():
    installation_result = subprocess.run("brew install --formula ./Formula/tezos-sapling-params.rb", shell=True)
    for binary in binaries:
        try:
            install_command_1 = f"brew install $(brew deps --include-build --formula \"./Formula/{binary}.rb\")"
            installation_result = subprocess.run(install_command_1, shell=True)
            assert installation_result.returncode == 0

            install_command_2 = f"brew install --formula --build-bottle \"./Formula/{binary}.rb\""
            installation_result = subprocess.run(install_command_2, shell=True)
            assert installation_result.returncode == 0

            check_binary_command = f"{binary.replace('tezos', 'octez')} --version"
            check_binary_result = subprocess.run(check_binary_command, shell=True)
            assert check_binary_result.returncode == 0
        except Exception as e:
            print(f"Exception happened when trying to execute tests for {binary}.\n")
            raise e

def get_deps():
    for binary in binaries:
        echo_command = f"echo \"|-----------------------------------{binary}-----------------------------------|\""
        subprocess.run(echo_command, shell=True)

        otool_command = f"otool -L $(which {binary})"
        otool_res = subprocess.run(otool_command, shell=True)
        assert otool_res.returncode == 0

        brew_command = f"brew deps {binary}"
        brew_result = subprocess.run(brew_command, shell=True)
        assert brew_result.returncode == 0

        echo_command = f"echo \"|------------------------------------------------------------------------------|\""
        subprocess.run(echo_command, shell=True)


if __name__ == "__main__":
    install()
    get_deps()

        #   brew install --formula ./Formula/tezos-sapling-params.rb
        #   brew install $(brew deps --include-build --formula "./Formula/tezos-client.rb")
        #   brew install --formula --build-bottle "./Formula/tezos-client.rb"