# SPDX-FileCopyrightText: 2022 Oxhead Alpha
# SPDX-License-Identifier: LicenseRef-MIT-OA

"""
Contains shared code from all Tezos wizards for a command line wizard skeleton.

Helps with writing a tool that asks questions, validates answers, and executes
the appropriate steps using the final configuration.
"""

import os, sys, subprocess, shlex, shutil
import re
import urllib.request
import json
from typing import List, Dict, Callable, Optional, Tuple, Union, Any
from dataclasses import dataclass, field
import tezos_baking.steps_common as steps
from tezos_baking.steps_common import Step, get_systemd_service_env, networks, key_import_modes, get_step_path
from tezos_baking.common import *
import tezos_baking.validators as validators


class Setup:
    def __init__(self, config={}, args=None):
        self.config = config
        self.args = args

    def query_step(self, step: Step):
        def interactive_query():
            validated = False
            while not validated:
                print(step.prompt)
                step.pprint_options()
                answer = input("> ").strip()
                if answer.lower() in ["quit", "exit"]:
                    raise KeyboardInterrupt
                elif answer.lower() in ["help", "?"]:
                    print(step.help)
                    print()
                else:
                    if not answer and step.default is not None:
                        answer = step.default
                    try:
                        step.process(answer, self.config)
                    except ValueError:
                        continue
                    else:
                        validated = True

        # check if step weren't already been fulfilled by cmd arguments
        if self.config.get(step.id, None) is None:

            steps_to_fill = get_step_path(self.args, step)
            if steps_to_fill:
                for (answer, step) in steps_to_fill:
                    step.process(answer, self.config)
            else:
                if self.args.non_interactive:
                    if step.default is not None:
                        step.process(step.default, self.config)
                    else:
                        print(f"Validation error: argument {step.id} is not supplied.", color_red)
                        raise ValueError(f"Missing argument: {step.id}")
                else:
                    interactive_query()

    def systemctl_simple_action(self, action, service):
        proc_call(
            f"sudo systemctl {action} tezos-{service}-{self.config['network']}.service"
        )

    def systemctl_enable(self):
        if self.config["systemd_mode"] == "yes":
            print(
                "Enabling the tezos-{}-{}.service".format(
                    self.config["mode"], self.config["network"]
                )
            )
            self.systemctl_simple_action("enable", self.config["mode"])
        else:
            print("The services won't restart on boot.")

    def get_tezos_client_options(self):
        options = (
            f"--base-dir {self.config['client_data_dir']} "
            f"--endpoint {self.config['node_rpc_endpoint']}"
        ) + f"--password-filename {self.config['password_filename']}" if self.config.get("password_filename", None) else ""
        if "remote_host" in self.config:
            options += f" -R '{self.config['remote_host']}'"
        return options

    def query_and_update_config(self, query):
        self.query_step(query)
        self.config["tezos_client_options"] = self.get_tezos_client_options()
        proc_call(
            f"sudo -u tezos {suppress_warning_text} octez-client "
            f"{self.config['tezos_client_options']} config update"
        )

    def fill_baking_config(self):
        net = self.config["network"]
        baking_env = get_systemd_service_env(f"tezos-baking-{net}")

        self.config["client_data_dir"] = baking_env.get(
            "TEZOS_CLIENT_DIR",
            "/var/lib/tezos/.tezos-client",
        )

        node_rpc_addr = baking_env.get(
            "NODE_RPC_ADDR",
            "localhost:8732",
        )
        self.config["node_rpc_addr"] = node_rpc_addr
        self.config["node_rpc_endpoint"] = "http://" + node_rpc_addr

        self.config["baker_alias"] = baking_env.get("BAKER_ADDRESS_ALIAS", "baker")

    def fill_remote_signer_infos(self):
        self.query_step(remote_signer_uri_query)

        rsu = re.search(signer_uri_regex.decode(), self.config["remote_signer_uri"])

        self.config["remote_host"] = rsu.group(1)
        self.config["remote_key"] = rsu.group(2)

    def get_current_head_level(self):
        response = urllib.request.urlopen(
            self.config["node_rpc_endpoint"] + "/chains/main/blocks/head/header"
        )
        return str(json.load(response)["level"])

    # Check if an account with the baker_alias alias already exists, and ask the user
    # if it can be overwritten.
    def check_baker_account(self):
        baker_alias = self.config["baker_alias"]
        baker_key_value = get_key_address(self.get_tezos_client_options(), baker_alias)
        if baker_key_value is not None:
            value, address = baker_key_value
            print()
            print("An account with the '" + baker_alias + "' alias already exists.")
            print("Its current address is", address)

            self.query_step(steps.replace_key_query)
            return self.config["replace_key"] == "yes"
        else:
            return True
#Use command
#  octez-client wait for oo7Tb626kbZaF6tLB8QYpKYqcW4daf5pvdk6MPuPNP5z9dpmBHo to be included --confirmations 1 --branch BMKa2VQpn5DGEZewLtLxWfgugPCKGa1viqpbAMsauXbbBMq1vcK
#and/or an external block explorer.
#You can check a blockchain explorer (e.g. https://tzkt.io/ or https://tzstats.com/)
#to see the baker status and baking rights of your account.
#
#Starting the baking instance
#🔐 Enter password for baker key: (press TAB for no echo)
#Broadcast message from root@ubuntu2204.localdomain (Wed 2023-05-03 09:59:26 UTC):
#
#Password entry required for 'Enter password for baker key:' (PID 3787).
#Please enter password with the systemd-tty-ask-password-agent tool.
#
#
#Job for tezos-baking-mumbainet.service failed because the control process exited with error code.
#See "systemctl status tezos-baking-mumbainet.service" and "journalctl -xeu tezos-baking-mumbainet.service" for details.
#
#Error in Tezos Setup Wizard, exiting.
#The error has been logged to /home/vagrant/tezos-packaging/tezos_setup.log
#  File "/usr/lib/python3.10/subprocess.py", line 369, in check_call
#    raise CalledProcessError(retcode, cmd)
#subprocess.CalledProcessError: Command '['sudo', 'systemctl', 'restart', 'tezos-baking-mumbainet.service']' returned non-zero exit status 1.
#
# понятно? нужно снова фиксить тезос пекежинг - давать возможность предоставить пароль в файле
    def import_key(self, key_mode_query, ledger_app=None):

        baker_alias = self.config["baker_alias"]
        tezos_client_options = self.get_tezos_client_options()

        valid_choice = False
        while not valid_choice:

            try:
                self.query_step(key_mode_query)

                if self.config["key_import_mode"] == "secret-key":
                    self.query_step(secret_key_query)
                    # i would prefer to keep non-interactive dispatching in the
                    # query_step only, but it is the only exception
                    if self.args.non_interactive:
                        encrypted = False
                        try:
                            validators.unencrypted_secret_key(self.config["secret_key"])
                        except ValueError:
                            encrypted = True
                        if encrypted:
                            # bad thing - in encrypted case it's still not really non-interactive because of systemd
                            # second thing - non-intractivity should be part of the model, because here it's really
                            # only need validator - you reproduced already existing logic
                            # we should also give ability to provide password file in interactive mode
                            #
                            #
                            # осталось точно реобработать флаги чтобы человеческие были и они переносились в вид который уже перевариваем в коде
                            self.query_step(steps.password_filename_query)

                    tezos_client_options = self.get_tezos_client_options()


                    proc_call(
                        f"sudo -u tezos {suppress_warning_text} octez-client {tezos_client_options} "
                        f"import secret key {baker_alias} {self.config['secret_key']} --force"
                    )
                elif self.config["key_import_mode"] == "remote":
                    self.fill_remote_signer_infos()

                    tezos_client_options = self.get_tezos_client_options()
                    proc_call(
                        f"sudo -u tezos {suppress_warning_text} octez-client {tezos_client_options} "
                        f"import secret key {baker_alias} remote:{self.config['remote_key']} --force"
                    )
                elif self.config["key_import_mode"] == "generate-fresh-key":
                    proc_call(
                        f"sudo -u tezos {suppress_warning_text} octez-client {tezos_client_options} "
                        f"gen keys {baker_alias} --force"
                    )
                    print("Newly generated baker key:")
                    proc_call(
                        f"sudo -u tezos {suppress_warning_text} octez-client {tezos_client_options} "
                        f"show address {baker_alias}"
                    )
                    network = self.config["network"]
                    print(
                        f"Before proceeding with baker registration you'll need to provide this address with some XTZ.\n"
                        f"Note that you need at least 6000 XTZ in order to receive baking and endorsing rights.\n"
                        f"You can fill your address using the faucet: https://faucet.{network}.teztnets.xyz/.\n"
                        f"Waiting for funds to arrive... (Ctrl + C to choose another option)."
                    )
                    try:
                        while True:
                            result = get_proc_output(
                                f"sudo -u tezos {suppress_warning_text} octez-client {tezos_client_options} "
                                f"register key {baker_alias} as delegate"
                            )
                            if result.returncode == 0:
                                print(result.stdout.decode("utf8"))
                                break
                            else:
                                proc_call("sleep 1")
                    except KeyboardInterrupt:
                        print("Going back to the import mode selection.")
                        continue
                elif self.config["key_import_mode"] == "json":
                    self.query_step(json_filepath_query)
                    json_tmp_path = shutil.copy(self.config["json_filepath"], "/tmp/")
                    proc_call(
                        f"sudo -u tezos {suppress_warning_text} octez-client {tezos_client_options} "
                        f"activate account {baker_alias} with {json_tmp_path} --force"
                    )
                    try:
                        os.remove(json_tmp_path)
                    except:
                        pass
                else:
                    print(f"Please open the Tezos {ledger_app} app on your ledger or")
                    print("press Ctrl+C to go back to the key import mode selection.")
                    ledgers_derivations = wait_for_ledger_app(
                        ledger_app, self.config["client_data_dir"]
                    )
                    if ledgers_derivations is None:
                        print("Going back to the import mode selection.")
                        continue
                    ledgers = list(ledgers_derivations.keys())
                    baker_ledger_url = ""
                    while re.match(ledger_regex.decode(), baker_ledger_url) is None:
                        self.query_step(
                            get_ledger_derivation_query(
                                ledgers_derivations,
                                self.config["node_rpc_endpoint"],
                                self.config["client_data_dir"],
                            )
                        )
                        if self.config["ledger_derivation"] == "Go back":
                            self.import_key(key_mode_query, ledger_app)
                            return
                        elif (
                            self.config["ledger_derivation"]
                            == "Specify derivation path"
                        ):
                            if len(ledgers) >= 1:
                                # If there is only one connected ledger, there is nothing to choose from
                                if len(ledgers) == 1:
                                    ledger_url = ledgers[0]
                                else:
                                    self.query_step(get_ledger_url_query(ledgers))
                                    ledger_url = self.config["ledger_url"]
                                self.query_step(derivation_path_query)
                                signing_curves = [
                                    "bip25519",
                                    "ed25519",
                                    "secp256k1",
                                    "P-256",
                                ]
                                for signing_curve in signing_curves:
                                    ledgers_derivations.setdefault(
                                        ledger_url, []
                                    ).append(
                                        signing_curve
                                        + "/"
                                        + self.config["derivation_path"]
                                    )
                        else:
                            baker_ledger_url = self.config["ledger_derivation"]
                    proc_call(
                        f"sudo -u tezos {suppress_warning_text} octez-client {tezos_client_options} "
                        f"import secret key {baker_alias} {baker_ledger_url} --force"
                    )

            except EOFError:
                raise EOFError
            except Exception as e:
                print("Something went wrong when calling octez-client:")
                print(str(e))
                print()
                print("Please check your input and try again.")
            else:
                valid_choice = True
                value, _ = get_key_address(
                    tezos_client_options, self.config["baker_alias"]
                )
                self.config["baker_key_value"] = value
