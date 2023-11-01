#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2021 Oxhead Alpha
# SPDX-License-Identifier: LicenseRef-MIT-OA

"""
A wizard utility to help set up tezos-baker.

Asks questions, validates answers, and executes the appropriate steps using the final configuration.
"""

import os, sys, shutil
import readline
import re
import traceback
import time
import urllib.request
import json
from typing import List
import logging


from tezos_baking.wizard_structure import *
from tezos_baking.util import *
from tezos_baking.steps import *
from tezos_baking.validators import Validator
import tezos_baking.validators as validators

# Global options

modes = {
    "baking": "Set up and start all services for baking: "
    "tezos-node and tezos-baker.",
    "node": "Only bootstrap and run the Tezos node.",
}

systemd_enable = {
    "yes": "Enable the services, running them both now and on every boot",
    "no": "Start the services this time only",
}

history_modes = {
    "rolling": "Store a minimal rolling window of chain data, lightest option",
    "full": "Store enough chain data to reconstruct the complete chain state",
    "archive": "Store all the chain data, very storage-demanding",
}

toggle_vote_modes = {
    "pass": "Abstain from voting",
    "off": "Request to end the subsidy",
    "on": "Request to continue or restart the subsidy",
}

default_providers = {
    "xtz-shots.io": "https://xtz-shots.io/tezos-snapshots.json",
    "marigold.dev": "https://snapshots.tezos.marigold.dev/api/tezos-snapshots.json",
}

recommended_provider = list(default_providers.keys())[0]

TMP_SNAPSHOT_LOCATION = "/tmp/octez_node.snapshot.d/"


# Wizard CLI utility


welcome_text = """Tezos Setup Wizard

Welcome, this wizard will help you to set up the infrastructure to interact with the
Tezos blockchain.

In order to run a baking instance, you'll need the following Tezos packages:
 tezos-client, tezos-node, tezos-baker-<proto>.
If you have installed tezos-baking, these packages are already installed.

All commands within the service are run under the 'tezos' user.

To access help and possible options for each question, type in 'help' or '?'.
Type in 'exit' to quit.
"""


def fetch_snapshot(url, sha256=None):

    logging.info("Fetching snapshot")

    dirname = TMP_SNAPSHOT_LOCATION
    filename = os.path.join(dirname, "octez_node.snapshot")
    metadata_file = os.path.join(dirname, "octez_node.snapshot.sha256")

    # updates or removes the 'metadata_file' containing the snapshot's SHA256
    def dump_metadata(metadata_file=metadata_file, sha256=sha256):
        if sha256:
            with open(metadata_file, "w+") as f:
                f.write(sha256)
        else:
            try:
                os.remove(metadata_file)
            except FileNotFoundError:
                pass

    # reads `metadata_file` if any or returns None
    def read_metadata(metadata_file=metadata_file):
        if os.path.exists(metadata_file):
            with open(metadata_file, "r") as f:
                sha256 = f.read()
            return sha256
        else:
            return None

    def download(filename=filename, url=url, args=""):
        from subprocess import CalledProcessError

        try:
            proc_call(f"wget {args} --show-progress -O {filename} {url}")
        except CalledProcessError as e:
            # see here https://www.gnu.org/software/wget/manual/html_node/Exit-Status.html
            if e.returncode >= 4:
                raise urllib.error.URLError
            else:
                raise e

    print_and_log(f"Downloading the snapshot from {url}")

    # expected for the (possibly) existing chunk
    expected_sha256 = read_metadata()

    os.makedirs(dirname, exist_ok=True)
    if sha256 and expected_sha256 and expected_sha256 == sha256:
        logging.info("Continuing download")
        # that case means that the expected sha256 of snapshot
        # we want to download is the same as the expected
        # sha256 of the existing octez_node.snapshot file
        # when it will be fully downloaded
        # so that we can safely use `--continue` option here
        download(args="--continue")
    else:
        # all other cases we just dump new metadata
        # (so that we can resume download if we can ensure
        # that existing octez_node.snapshot chunk belongs
        # to the snapshot we want to download)
        # and start download from scratch
        dump_metadata()
        download()

    print()
    return filename


class Sha256Mismatch(Exception):
    "Raised when the actual and expected sha256 don't match."

    def __init__(self, actual_sha256=None, expected_sha256=None):
        self.actual_sha256 = actual_sha256
        self.expected_sha256 = expected_sha256


class InterruptStep(Exception):
    "Raised when there is need to interrupt step handling flow."


def check_file_contents_integrity(filename, sha256):
    import hashlib

    sha256sum = hashlib.sha256()
    with open(filename, "rb") as f:
        contents = f.read()
    sha256sum.update(contents)

    actual_sha256 = str(sha256sum.hexdigest())
    expected_sha256 = sha256

    if actual_sha256 != expected_sha256:
        raise Sha256Mismatch(actual_sha256, expected_sha256)


def is_full_snapshot(snapshot_file, import_mode):
    if import_mode == "download full":
        return True
    if import_mode == "file" or import_mode == "url":
        output = get_proc_output(
            "sudo -u tezos octez-node snapshot info " + snapshot_file
        ).stdout
        return re.search(b"at level [0-9]+ in full", output) is not None
    return False


def get_node_version():
    version = get_proc_output("octez-node --version").stdout.decode("ascii")
    major_version, minor_version, rc_version = re.search(
        r"[a-z0-9]+ \(.*\) \(([0-9]+).([0-9]+)(?:(?:~rc([1-9]+))|(?:\+dev))?\)",
        version,
    ).groups()
    return (
        int(major_version),
        int(minor_version),
        (int(rc_version) if rc_version is not None else None),
    )


compatible_snapshot_version = 6


# Steps

network_query = Step(
    id="network",
    prompt="Which Tezos network would you like to use?\nCurrently supported:",
    help="The selected network will be used to set up all required services.\n"
    "The currently supported protocol is `PtNairob` (used on `nairobinet`, `ghostnet` and `mainnet`).\n"
    "Keep in mind that you must select the test network (e.g. ghostnet)\n"
    "if you plan on baking with a faucet JSON file.\n",
    options=networks,
    validator=Validator(validators.enum_range(networks)),
)

service_mode_query = Step(
    id="mode",
    prompt="Do you want to set up baking or to run the standalone node?",
    help="By default, tezos-baking provides predefined services for running baking instances "
    "on different networks.\nSometimes, however, you might want to only run the Tezos node.\n"
    "When this option is chosen, this wizard will help you bootstrap the Tezos node only.",
    options=modes,
    validator=Validator(validators.enum_range(modes)),
)

systemd_mode_query = Step(
    id="systemd_mode",
    prompt="Would you like your setup to automatically start on boot?",
    help="Starting the service will make it available just for this session, great\n"
    "if you want to experiment. Enabling it will make it start on every boot.",
    options=systemd_enable,
    validator=Validator(validators.enum_range(systemd_enable)),
)

liquidity_toggle_vote_query = Step(
    id="liquidity_toggle_vote",
    prompt="Would you like to request to end the Liquidity Baking subsidy?",
    help="Tezos chain offers a Liquidity Baking subsidy mechanism to incentivise exchange\n"
    "between tez and tzBTC. You can ask to end this subsidy, ask to continue it, or abstain.\n"
    "\nYou can read more about this in the here:\n"
    "https://tezos.gitlab.io/active/liquidity_baking.html",
    options=toggle_vote_modes,
    validator=Validator(validators.enum_range(toggle_vote_modes)),
)

# We define this step as a function to better tailor snapshot options to the chosen history mode
def get_snapshot_mode_query(config):

    static_import_modes = {
        "file": Option("file", "Import snapshot from a file", requires=snapshot_file_query),
        "direct url": Option("direct url", "Import snapshot from a direct url", requires=snapshot_url_query),
        "provider url": Option("provider url", "Import snapshot from a provider", requires=provider_url_query),
        "skip": "Skip snapshot import and synchronize with the network from scratch",
    }

    history_mode = config["history_mode"]

    mk_option = lambda pr, hm=history_mode: f"download {hm} ({pr})"
    mk_desc = lambda pr, hm=history_mode: f"Import {hm} snapshot from {pr}" + (
        " (recommended)" if pr == recommended_provider else ""
    )

    dynamic_import_modes = {}

    for name in default_providers.keys():
        if config["snapshots"].get(name, None):
            dynamic_import_modes[mk_option(name)] = mk_desc(name)

    import_modes = {**dynamic_import_modes, **static_import_modes}

    return Step(
        id="snapshot_mode",
        prompt="The Tezos node can take a significant time to bootstrap from scratch.\n"
        "Bootstrapping from a snapshot is suggested instead.\n"
        "How would you like to proceed?",
        help="A fully-synced local Tezos node is required for running a baking instance.\n"
        "By default, the Tezos node service will start to bootstrap from scratch,\n"
        "which will take a significant amount of time.\nIn order to avoid this, we suggest "
        "bootstrapping from a snapshot instead.\n\n"
        "Snapshots can be downloaded from the following websites:\n"
        "Marigold - https://snapshots.tezos.marigold.dev/ \n"
        "XTZ-Shots - https://xtz-shots.io/ \n\n"
        "We recommend to use rolling snapshots. This is the smallest and the fastest mode\n"
        "that is sufficient for baking. You can read more about other Tezos node history modes here:\n"
        "https://tezos.gitlab.io/user/history_modes.html#history-modes",
        options=import_modes,
        validator=Validator(validators.enum_range(import_modes)),
    )


delete_node_data_options = {
    "no": "Keep the existing data",
    "yes": "Remove the data under the tezos node data directory",
}

delete_node_data_query = Step(
    id="delete_node_data",
    prompt="Delete this data and bootstrap the node again?",
    help="It's possible to proceed with bootstrapping the node using\n"
    "the existing blockchain data, instead of importing fresh snapshot.",
    options=delete_node_data_options,
    validator=Validator(validators.enum_range(delete_node_data_options)),
)

snapshot_file_query = Step(
    id="snapshot_file",
    prompt="Provide the path to the node snapshot file.",
    help="You have indicated wanting to import the snapshot from a file.\n"
    "You can download the snapshot yourself e.g. from XTZ-Shots or Tezos Giganode Snapshots.",
    default=None,
    validator=Validator([validators.required_field, validators.filepath]),
)

provider_url_query = Step(
    id="provider_url",
    prompt="Provide the url of the snapshot provider.",
    help="You have indicated wanting to fetch the snapshot from a custom provider.\n",
    default=None,
    validator=Validator([validators.required_field, validators.reachable_url()]),
)

snapshot_url_query = Step(
    id="snapshot_url",
    prompt="Provide the url of the node snapshot file.",
    help="You have indicated wanting to import the snapshot from a custom url.\n"
    "You can use e.g. links to XTZ-Shots or Marigold resources.",
    default=None,
    validator=Validator([validators.required_field, validators.reachable_url()]),
)

snapshot_sha256_query = Step(
    id="snapshot_sha256",
    prompt="Provide the sha256 of the node snapshot file. (optional)",
    help="With sha256 provided, an integrity check will be performed for you.\n"
    "Also, it will be possible to resume incomplete snapshot downloads.",
    default=None,
)

history_mode_query = Step(
    id="history_mode",
    prompt="Which history mode do you want your node to run in?",
    help="History modes govern how much data a Tezos node stores, and, consequently, how much disk\n"
    "space is required. Rolling mode is the smallest and fastest but still sufficient for baking.\n"
    "You can read more about different nodes history modes here:\n"
    "https://tezos.gitlab.io/user/history_modes.html",
    options=history_modes,
    validator=Validator(validators.enum_range(history_modes)),
)

# We define the step as a function to disallow choosing json baking on mainnet
def get_key_mode_query(modes):
    return Step(
        id="key_import_mode",
        prompt="How do you want to import the baker key?",
        help="To register the baker, its secret key needs to be imported to the data "
        "directory first.\nBy default tezos-baking-<network>.service will use the 'baker' "
        "alias\nfor the key that will be used for baking and endorsing.\n"
        "If you want to test baking with a faucet file, "
        "make sure you have chosen a test network like " + list(networks.keys())[1],
        options=modes,
        validator=Validator(validators.enum_range(modes)),
    )


ignore_hash_mismatch_options = {
    "no": "Discard the snapshot and return to the previous step",
    "yes": "Continue the setup with this snapshot",
}

ignore_hash_mismatch_query = Step(
    id="ignore_hash_mismatch",
    prompt="Do you want to proceed with this snapshot anyway?",
    help="It's possible, but not recommended, to ignore the sha256 mismatch and use this snapshot anyway.",
    options=ignore_hash_mismatch_options,
    validator=Validator(validators.enum_range(ignore_hash_mismatch_options)),
)

# CLI argument parser

parser = argparse.ArgumentParser()
parser.add_argument("--network", type=str)
parser.add_argument("--mode", type=str)
parser.add_argument("--enable", type=str, dest="systemd_mode")
parser.add_argument("--liquidity-toggle-vote", type=str)
parser.add_argument("--snapshot", type=str)
parser.add_argument("--file", type=str, metavar="SNAPSHOT_FILE", dest="snapshot_file")
parser.add_argument("--url", type=str, metavar="SNAPSHOT_URL", dest="snapshot_url")
parser.add_argument("--sha256", type=str, metavar="SNAPSHOT_URL", dest="snapshot_sha256")
parser.add_argument("--history-mode", type=str)
parser.add_argument("--key-import-mode", type=str)


class Setup(Setup):
    # Check if there is already some blockchain data in the octez-node data directory,
    # and ask the user if it can be overwritten.
    def check_blockchain_data(self):
        logging.info("Checking blockchain data")
        node_dir = get_data_dir(self.config["network"])
        node_dir_contents = set()
        try:
            node_dir_contents = set(os.listdir(node_dir))
        except FileNotFoundError:
            print_and_log("The Tezos node data directory does not exist.")
            print_and_log("  Creating directory: " + node_dir)
            proc_call("sudo mkdir " + node_dir)
            proc_call("sudo chown tezos:tezos " + node_dir)

        # Content expected in a configured and clean node data dir
        node_dir_config = set(["config.json", "version.json"])

        # Configure data dir if the config is missing
        if not node_dir_config.issubset(node_dir_contents):
            print_and_log("The Tezos node data directory has not been configured yet.")
            print_and_log("  Configuring directory: " + node_dir)
            proc_call(
                "sudo -u tezos octez-node-"
                + self.config["network"]
                + " config init"
                + " --network "
                + self.config["network"]
                + " --rpc-addr "
                + self.config["node_rpc_addr"]
            )

        diff = node_dir_contents - node_dir_config
        if diff:
            logging.info(
                "The Tezos node data directory already has some blockchain data"
            )
            print("The Tezos node data directory already has some blockchain data:")
            print("\n".join(["- " + os.path.join(node_dir, path) for path in diff]))
            self.query_step(delete_node_data_query)
            if self.config["delete_node_data"] == "yes":
                # We first stop the node service, because it's possible that it
                # will re-create some of the files while we go on with the wizard
                print_and_log("Stopping node service")
                proc_call(
                    "sudo systemctl stop tezos-node-"
                    + self.config["network"]
                    + ".service"
                )
                for path in diff:
                    try:
                        proc_call("sudo rm -r " + os.path.join(node_dir, path))
                    except:
                        logging.error("Could not clean the Tezos node data directory.")
                        print(
                            "Could not clean the Tezos node data directory. "
                            "Please do so manually."
                        )
                        raise OSError(
                            "'sudo rm -r " + os.path.join(node_dir, path) + "' failed."
                        )

                print_and_log("Node directory cleaned.")
                return True
            return False
        return True

    # Returns relevant snapshot's metadata
    # It filters out provided snapshots by `network` and `history_mode`
    # provided by the user and then follows this steps:
    # * tries to find the snapshot of exact same Octez version, that is used by the user.
    # * if there is none, try to find the snapshot with the same major version, but less minor version
    #   and with the `snapshot_version` compatible with the user's Octez version.
    # * If there is none, try to find the snapshot with any Octez version, but compatible `snapshot_version`.
    def extract_relevant_snapshot(self, snapshot_array):
        from functools import reduce

        def find_snapshot(pred):
            return next(
                filter(
                    lambda artifact: artifact["artifact_type"] == "tezos-snapshot"
                    and artifact["chain_name"] == self.config["network"]
                    and (
                        artifact["history_mode"] == self.config["history_mode"]
                        or (
                            self.config["history_mode"] == "archive"
                            and artifact["history_mode"] == "full"
                        )
                    )
                    and pred(
                        *(
                            get_artifact_node_version(artifact)
                            + (artifact.get("snapshot_version", None),)
                        )
                    ),
                    iter(snapshot_array),
                ),
                None,
            )

        def get_artifact_node_version(artifact):
            version = artifact["tezos_version"]["version"]
            # there seem to be some inconsistency with that field in different providers
            # so the only thing we check is if it's a string
            additional_info = version["additional_info"]
            return (
                version["major"],
                version["minor"],
                None if type(additional_info) == str else additional_info["rc"],
            )

        def compose_pred(*preds):
            return reduce(
                lambda acc, x: lambda major, minor, rc, snapshot_version: acc(
                    major, minor, rc, snapshot_version
                )
                and x(major, minor, rc, snapshot_version),
                preds,
            )

        def sum_pred(*preds):
            return reduce(
                lambda acc, x: lambda major, minor, rc, snapshot_version: acc(
                    major, minor, rc, snapshot_version
                )
                or x(major, minor, rc, snapshot_version),
                preds,
            )

        node_version = get_node_version()
        major_version, minor_version, rc_version = node_version

        exact_version_pred = (
            lambda major, minor, rc, snapshot_version: node_version
            == (
                major,
                minor,
                rc,
            )
        )

        exact_major_version_pred = (
            lambda major, minor, rc, snapshot_version: major_version == major
        )

        exact_minor_version_pred = (
            lambda major, minor, rc, snapshot_version: minor_version == minor
        )

        less_minor_version_pred = (
            lambda major, minor, rc, snapshot_version: minor_version > minor
        )

        exact_rc_version_pred = (
            lambda major, minor, rc, snapshot_version: rc_version == rc
        )

        less_rc_version_pred = (
            lambda major, minor, rc, snapshot_version: rc
            and rc_version
            and rc_version > rc
        )

        non_rc_version_pred = lambda major, minor, rc, snapshot_version: rc is None

        compatible_version_pred = (
            # it could happen that `snapshot_version` field is not supplied by provider
            # e.g. marigold snapshots don't supply it
            lambda major, minor, rc, snapshot_version: snapshot_version
            and compatible_snapshot_version == snapshot_version
        )

        non_rc_on_stable_pred = lambda major, minor, rc, snapshot_version: (
            rc_version is None and rc is None
        ) or (rc_version is not None)

        preds = [
            exact_version_pred,
            compose_pred(
                non_rc_on_stable_pred,
                compatible_version_pred,
                sum_pred(
                    compose_pred(
                        exact_major_version_pred,
                        exact_minor_version_pred,
                        less_rc_version_pred,
                    ),
                    compose_pred(
                        exact_major_version_pred,
                        less_minor_version_pred,
                        non_rc_version_pred,
                    ),
                ),
            ),
            compose_pred(
                non_rc_on_stable_pred,
                compatible_version_pred,
            ),
        ]

        return next(
            (
                snapshot
                for snapshot in map(
                    lambda pred: find_snapshot(pred),
                    preds,
                )
                if snapshot is not None
            ),
            None,
        )

    # Check the provider url and collect the most recent snapshot
    # that is suited for the chosen history mode and network
    def get_snapshot_metadata(self, name, json_url):

        try:
            snapshot_array = None
            with urllib.request.urlopen(json_url) as url:
                snapshot_array = json.load(url)["data"]
            snapshot_array.sort(reverse=True, key=lambda x: x["block_height"])

            snapshot_metadata = self.extract_relevant_snapshot(snapshot_array)

            if snapshot_metadata is None:
                message = f"No suitable snapshot found from the {name} provider."
                print(
                    color(
                        message,
                        color_red,
                    )
                )
                logging.warning(message)
            else:
                self.config["snapshots"][name] = snapshot_metadata

        except urllib.error.URLError:
            message = f"\nCouldn't collect snapshot metadata from {json_url} due to networking issues.\n"
            print(
                color(
                    message,
                    color_red,
                )
            )
            logging.error(message)
        except ValueError:
            message = f"\nCouldn't collect snapshot metadata from {json_url} due to format mismatch.\n"
            print(
                color(
                    message,
                    color_red,
                )
            )
            logging.error(message)
        except Exception as e:
            print_and_log(f"\nUnexpected error handling snapshot metadata:\n{e}\n")

    def output_snapshot_metadata(self, name):
        from datetime import datetime
        from locale import setlocale, getlocale, LC_TIME

        # it is portable `C` locale by default
        setlocale(LC_TIME, getlocale())

        metadata = self.config["snapshots"][name]
        timestamp_dt = datetime.strptime(
            metadata["block_timestamp"], "%Y-%m-%dT%H:%M:%SZ"
        )
        timestamp = timestamp_dt.strftime("%c")
        delta = datetime.now() - timestamp_dt
        time_ago = (
            "less than 1 day ago"
            if delta.days == 0
            else "1 day ago"
            if delta.days == 1
            else f"{delta.days} days ago"
        )
        print(
            color(
                f"""
Snapshot metadata:
url: {metadata["url"]}
sha256: {metadata["sha256"]}
filesize: {metadata["filesize"]}
block height: {metadata["block_height"]}
block timestamp: {timestamp} ({time_ago})
""",
                color_green,
            )
        )

    def fetch_snapshot_from_provider(self, name):
        try:
            url = self.config["snapshots"][name]["url"]
            sha256 = self.config["snapshots"][name]["sha256"]
            self.output_snapshot_metadata(name)
            return fetch_snapshot(url, sha256)
        except KeyError:
            raise InterruptStep
        except (ValueError, urllib.error.URLError):
            logging.error(
                "The snapshot snapshot download option user have chosen is unavailable"
            )
            print("The snapshot download option you chose is unavailable,")
            print("which normally shouldn't happen. Please check your")
            print("internet connection or choose another option.")
            print()
            raise InterruptStep

    def get_snapshot_from_provider(self, name, url):
        try:
            self.config["snapshots"][name]
        except KeyError:
            self.get_snapshot_metadata(name, url)
        snapshot_file = self.fetch_snapshot_from_provider(name)
        snapshot_block_hash = self.config["snapshots"][name]["block_hash"]
        return (snapshot_file, snapshot_block_hash)

    def get_snapshot_from_direct_url(self, url):
        try:
            self.query_step(snapshot_sha256_query)
            sha256 = self.config["snapshot_sha256"]
            snapshot_file = fetch_snapshot(url, sha256)
            if sha256:
                print_and_log("Checking the snapshot integrity...")
                check_file_contents_integrity(snapshot_file, sha256)
                print_and_log("Integrity verified.")
            return (snapshot_file, None)
        except (ValueError, urllib.error.URLError):
            print()
            logging.error("The snapshot url provided is unavailable.")
            print("The snapshot URL you provided is unavailable.")
            print("Please check the URL again or choose another option.")
            print()
            raise InterruptStep
        except Sha256Mismatch as e:
            print_and_log("SHA256 mismatch.", logging.error)
            print_and_log(f"Expected sha256: {e.expected_sha256}", logging.error)
            print_and_log(f"Actual sha256: {e.actual_sha256}", logging.error)
            print()
            if self.config["ignore_hash_mismatch"] == "no":
                raise InterruptStep
            else:
                logging.info("Ignoring hash mismatch")
                return (snapshot_file, None)

    def get_snapshot_from_provider_url(self, url):
        name = "custom"
        if os.path.basename(url) == "tezos-snapshots.json":
            return self.get_snapshot_from_provider(name, url)
        else:
            try:
                return self.get_snapshot_from_provider(name, url)
            except InterruptStep:
                return self.get_snapshot_from_provider(
                    name, os.path.join(url, "tezos-snapshots.json")
                )

    # Importing the snapshot for Node bootstrapping
    def import_snapshot(self):
        do_import = self.check_blockchain_data()
        valid_choice = False

        if do_import:
            self.query_step(history_mode_query)

            logging.info("Updating history mode octez-node config")
            proc_call(
                f"sudo -u tezos octez-node-{self.config['network']} config update "
                f"--history-mode {self.config['history_mode']}"
            )

            self.config["snapshots"] = {}

            if args.getattr("file")
            print_and_log("Getting snapshots' metadata from providers...")
            for name, url in default_providers.items():
                self.get_snapshot_metadata(name, url)

            os.makedirs(TMP_SNAPSHOT_LOCATION, exist_ok=True)

        else:
            return

        while not valid_choice:

            self.query_step(get_snapshot_mode_query(self.config))

            snapshot_file = TMP_SNAPSHOT_LOCATION
            snapshot_block_hash = None

            try:
                if self.config["snapshot_mode"] == "skip":
                    return
                elif self.config["snapshot_mode"] == "file":
                    self.query_step(snapshot_file_query)
                    snapshot_file = os.path.join(
                        TMP_SNAPSHOT_LOCATION, f"file-{time.time()}.snapshot"
                    )
                    # not copying since it can take a lot of time
                    os.link(self.config["snapshot_file"], snapshot_file)
                elif self.config["snapshot_mode"] == "direct url":
                    self.query_step(snapshot_url_query)
                    url = self.config["snapshot_url"]
                    (
                        snapshot_file,
                        snapshot_block_hash,
                    ) = self.get_snapshot_from_direct_url(url)
                elif self.config["snapshot_mode"] == "provider url":
                    self.query_step(provider_url_query)
                    name, url = "custom", self.config["provider_url"]
                    (
                        snapshot_file,
                        snapshot_block_hash,
                    ) = self.get_snapshot_from_provider_url(url)
                else:
                    for name, url in default_providers.items():
                        if name in self.config["snapshot_mode"]:
                            (
                                snapshot_file,
                                snapshot_block_hash,
                            ) = self.get_snapshot_from_provider(name, url)
            except InterruptStep:
                print_and_log("Getting back to the snapshot import mode step.")
                continue

            valid_choice = True

            import_flag = ""
            if is_full_snapshot(snapshot_file, self.config["snapshot_mode"]):
                if self.config["history_mode"] == "archive":
                    import_flag = "--reconstruct "

            block_hash_option = ""
            if snapshot_block_hash is not None:
                block_hash_option = " --block " + snapshot_block_hash

            logging.info("Importing snapshot with the octez-node")
            proc_call(
                "sudo -u tezos octez-node-"
                + self.config["network"]
                + " snapshot import "
                + import_flag
                + snapshot_file
                + block_hash_option
            )

            print_and_log("Snapshot imported.")

            try:
                shutil.rmtree(TMP_SNAPSHOT_LOCATION)
            except:
                pass
            else:
                print_and_log("Deleted the temporary snapshot file.")

    # Bootstrapping octez-node
    def bootstrap_node(self):

        self.import_snapshot()

        logging.info("Starting the node service")
        print(
            "Starting the node service. This is expected to take some "
            "time, as the node needs a node identity to be generated."
        )

        self.systemctl_simple_action("start", "node")

        print_and_log("Waiting for the node service to start...")

        while True:
            rpc_endpoint = self.config["node_rpc_endpoint"]
            try:
                urllib.request.urlopen(rpc_endpoint + "/version")
                break
            except urllib.error.URLError:
                proc_call("sleep 1")

        print_and_log("Generated node identity and started the service.")

        self.systemctl_enable()

        if self.config["mode"] == "node":
            logging.info("The node setup is finished.")
            print(
                "The node setup is finished. It will take some time for the node to bootstrap.",
                "You can check the progress by running the following command:",
            )
            print(f"systemctl status tezos-node-{self.config['network']}.service")

            print()
            print_and_log("Exiting the Tezos Setup Wizard.")
            sys.exit(0)

        print_and_log("Waiting for the node to be bootstrapped...")

        tezos_client_options = self.get_tezos_client_options()
        proc_call(
            f"sudo -u tezos {suppress_warning_text} octez-client {tezos_client_options} bootstrapped"
        )

        print()
        print_and_log("The Tezos node bootstrapped successfully.")

    # Importing the baker key
    def import_baker_key(self):
        baker_alias = self.config["baker_alias"]
        tezos_client_options = self.get_tezos_client_options()
        replace_baker_key = self.check_baker_account()

        if replace_baker_key:
            if self.config["network"] == "mainnet":
                key_import_modes.pop("json", None)
                key_import_modes.pop("generate-fresh-key", None)
            key_mode_query = get_key_mode_query(key_import_modes)

            baker_set_up = False
            while not baker_set_up:
                self.import_key(key_mode_query, "Baking")

                if self.config["key_import_mode"] == "ledger":
                    try:
                        print(
                            color(
                                "Waiting for your response to the prompt on your Ledger Device...",
                                color_green,
                            )
                        )
                        logging.info("Running octez-client to setup ledger")
                        proc_call(
                            f"sudo -u tezos {suppress_warning_text} octez-client {tezos_client_options} "
                            f"setup ledger to bake for {baker_alias} --main-hwm {self.get_current_head_level()}"
                        )
                        baker_set_up = True
                    except Exception as e:
                        print("Something went wrong when calling octez-client:")
                        print_and_log(str(e), logging.error)
                        print()
                        print("Please check your input and try again.")
                        print_and_log(
                            "Going back to the import mode selection.", logging.error
                        )

                else:
                    baker_set_up = True

    def register_baker(self):
        print()
        tezos_client_options = self.get_tezos_client_options()
        baker_alias = self.config["baker_alias"]
        if self.config["key_import_mode"] == "ledger":
            print(
                color(
                    "Waiting for your response to the prompt on your Ledger Device...",
                    color_green,
                )
            )
        proc_call(
            f"sudo -u tezos {suppress_warning_text} octez-client {tezos_client_options} "
            f"register key {baker_alias} as delegate"
        )
        print(
            "You can check a blockchain explorer (e.g. https://tzkt.io/ or https://tzstats.com/)\n"
            "to see the baker status and baking rights of your account."
        )

    # There is no changing the toggle vote option at a glance,
    # so we need to change the config every time
    def set_liquidity_toggle_vote(self):
        self.query_step(liquidity_toggle_vote_query)

        net = self.config["network"]
        logging.info(
            "Replacing tezos-baking service env with liquidity toggle vote setting"
        )
        replace_systemd_service_env(
            f"tezos-baking-{net}",
            "LIQUIDITY_BAKING_TOGGLE_VOTE",
            f"\"{self.config['liquidity_toggle_vote']}\"",
        )

    def start_baking(self):
        self.systemctl_simple_action("restart", "baking")

    def run_setup(self):

        logging.info("Starting the Tezos Setup Wizard.")

        print(welcome_text)

        self.query_step(network_query)
        self.fill_baking_config()
        self.query_step(service_mode_query)

        print()
        self.query_step(systemd_mode_query)

        print_and_log("Trying to bootstrap octez-node")
        self.bootstrap_node()

        # If we continue execution here, it means we need to set up baking as well.
        executed = False
        while not executed:
            print()
            print_and_log("Importing the baker key")
            self.import_baker_key()

            print()
            print_and_log("Registering the baker")
            try:
                self.register_baker()
            except EOFError:
                logging.error("Got EOF")
                raise EOFError
            except Exception as e:
                print_and_log(
                    "Something went wrong when calling octez-client:", logging.error
                )
                print_and_log(str(e), logging.error)
                print()
                print("Going back to the previous step.")
                print("Please check your input and try again.")
                continue
            executed = True

        self.set_liquidity_toggle_vote()

        print()
        print_and_log("Starting the baking instance")
        self.start_baking()

        print()
        print(
            "Congratulations! All required Tezos infrastructure services should now be started."
        )
        print(
            "You can show logs for all the services using the 'tezos' user by running:"
        )
        print("journalctl -f _UID=$(id tezos -u)")

        print()
        print("To stop the baking instance, run:")
        print(f"sudo systemctl stop tezos-baking-{self.config['network']}.service")

        print()
        print(
            "If you previously enabled the baking service and want to disable it, run:"
        )
        print(f"sudo systemctl disable tezos-baking-{self.config['network']}.service")
        logging.info("Exiting the Tezos Setup Wizard.")


def main():
    readline.parse_and_bind("tab: complete")
    readline.set_completer_delims(" ")

    try:
        setup_logger("tezos-setup.log")
        args = parser.parse_args()
        setup = Setup(args=args)
        setup.run_setup()
    except KeyboardInterrupt as e:
        if "network" in setup.config:
            proc_call(
                "sudo systemctl stop tezos-baking-"
                + setup.config["network"]
                + ".service"
            )
        logging.info(f"Received keyboard interrupt.")
        print_and_log("Exiting the Tezos Setup Wizard.")
        sys.exit(1)
    except EOFError as e:
        if "network" in setup.config:
            proc_call(
                "sudo systemctl stop tezos-baking-"
                + setup.config["network"]
                + ".service"
            )
        logging.info(f"Reached EOF.")
        print_and_log("Exiting the Tezos Setup Wizard.")
        sys.exit(1)
    except Exception as e:
        if "network" in setup.config:
            proc_call(
                "sudo systemctl stop tezos-baking-"
                + setup.config["network"]
                + ".service"
            )
        logging.error(f"{str(e)}")
        print_and_log("Error in Tezos Setup Wizard, exiting.")
        logfile = "tezos_setup.log"
        with open(logfile, "a") as f:
            f.write(traceback.format_exc() + "\n")
        print("The error has been logged to", os.path.abspath(logfile))
        sys.exit(1)


if __name__ == "__main__":
    main()
