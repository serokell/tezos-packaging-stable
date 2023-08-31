# SPDX-FileCopyrightText: 2023 Oxhead Alpha
# SPDX-License-Identifier: LicenseRef-MIT-OA

from typing import List, Dict, Callable, Optional, Tuple, Union, Any, Mapping
from dataclasses import dataclass, field
import textwrap
import sys

from tezos_baking.common import *
import tezos_baking.validators as validators


@dataclass
class Option:
    item: str
    description: str
    requires: "Step"


@dataclass
class Step:
    id: str
    help: str
    prompt: str
    default: Optional[str] = None
    options: Mapping[str, Union[str, Option]] = field(default_factory=lambda: {})
    validator: Union[
        List[Callable[[str], str]],
        Callable[[Dict[str, str]], Callable[[str], str]],
    ] = (lambda x: lambda y: y)
    actions: List[Callable[[str, Dict[str, str]], None]] = field(default_factory=lambda: [])


    def process(self, answer: str, config: Dict[str, str]):
        try:
            answer = self.validate(answer)
        except ValueError as e:
            print(color("Validation error: " + str(e), color_red))
            raise e
        else:
            config[self.id] = answer
            for fill in self.actions:
                fill(answer, config)


    def validate(self, input):
        if isinstance(self.validator, list):
            for v in self.validator:
                input = v(input)
            return input
        else:
            return self.validator(self.options)(input)


    def pprint_options(self):
        i = 1
        def_i = None
        try:
            def_i = int(self.default)
        except:
            pass

        if self.options and isinstance(self.options, list):
            options_count = 0
            for o in self.options:
                if isinstance(o, dict):
                    for values in o.values():
                        if not isinstance(values, list):
                            options_count += 1
                        else:
                            options_count += len(values)
                else:
                    options_count += 1
            index_len = len(str(options_count))
            str_format = f"{{:{index_len}}}. {{}}"
            for o in self.options:
                if isinstance(o, dict):
                    for k, values in o.items():
                        print()
                        print(f"'{k}':")
                        print()
                        if not isinstance(values, list):
                            values = [values]
                        for v in values:
                            if def_i is not None and i == def_i:
                                print(str_format.format(i, "(default) " + v))
                            else:
                                print(str_format.format(i, v))
                            i += 1
                    print()
                else:
                    if def_i is not None and i == def_i:
                        print(str_format.format(i, "(default) " + o))
                    else:
                        print(str_format.format(i, o))
                    i += 1
        elif self.options and isinstance(self.options, dict):
            index_len = len(str(len(self.options)))
            max_option_len = max(map(len, self.options.keys()))
            padding = max(26, max_option_len + 2)
            indent_size = index_len + 4 + padding
            str_format = f"{{:{index_len}}}. {{:<{padding}}}  {{}}"
            for o in self.options:
                prompt = self.options[o] if isinstance(self.options[o], str) else self.options[o].description
                description = textwrap.indent(
                    textwrap.fill(prompt, 60),
                    " " * indent_size,
                ).lstrip()
                if def_i is not None and i == def_i:
                    print(str_format.format(i, o + " (default)", description))
                else:
                    print(str_format.format(i, o, description))
                i += 1
        elif not self.options and self.default is not None:
            print("Default:", self.default)


def get_step_path(args, step: Step) -> List[Tuple[str, Step]]:
    argument: Optional[str] = getattr(args, step.id, None)
    if argument is None:
        paths = []
        for (k, v) in step.options.items():
            if isinstance(v, str):
                continue
            path = get_step_path(args, v.requires)
            if path:
                paths.append((v.item, path))
        if len(paths) > 1:
            raise ValueError(f"Conflicting arguments: {', '.join(path[1][-1][1].id for path in paths)}")
        elif len(paths) == 1:
            (answer, path) = paths[0]
            return [(answer, step)] + path
        else:
            return []
    else:
        return [(argument, step)]


networks = {
    "mainnet": "Main Tezos network",
    "ghostnet": "Long running test network, currently using the Nairobi Tezos protocol",
    "nairobinet": "Test network using the Nairobi Tezos protocol",
    "oxfordnet": "Test network using the Oxford Tezos protocol",
}

# надо сделать чтобы non-interactive всплывал исключительно в query_step
# ввести в модель понятие неявных шагов, которые не появляются в интерактивном режиме
# но нужны в неинтерактивном

# Steps

secret_key_query = Step(
    id="secret_key",
    prompt="Provide either the unencrypted or password-encrypted secret key for your address.",
    help="The format is 'unencrypted:edsk...' for the unencrypted key, or 'encrypted:edesk...'"
    "for the encrypted key.",
    default=None,
    validator=[validators.required_field, validators.secret_key],
)


key_import_modes = {
    "ledger": "From a ledger",
    "secret-key": Option("secret-key", "Either the unencrypted or password-encrypted secret key for your address", requires=secret_key_query),
    "remote": "Remote key governed by a signer running on a different machine",
    "generate-fresh-key": "Generate fresh key that should be filled manually later",
    "json": "Faucet JSON file",
}


def remote_signer_url_action(answer: str, config: Dict[str, str]):
    rsu = re.search(signer_uri_regex.decode(), config["remote_signer_uri"])
    config["remote_host"] = rsu.group(1)
    config["remote_key"] = rsu.group(2)


remote_signer_uri_query = Step(
    id="remote_signer_uri",
    prompt="Provide your remote key with the address of the signer.",
    help="The format is the address of your remote signer host, followed by a public key,\n"
    "i.e. something like http://127.0.0.1:6732/tz1V8fDHpHzN8RrZqiYCHaJM9EocsYZch5Cy\n"
    "The supported schemes are https, http, tcp, and unix.",
    default=None,
    validator=[validators.required_field, validators.signer_uri],
    actions=[remote_signer_url_action],
)

derivation_path_query = Step(
    id="derivation_path",
    prompt="Provide derivation path for the key stored on the ledger.",
    help="The format is '[0-9]+h/[0-9]+h'",
    validator=[validators.required_field, validators.derivation_path],
)

json_filepath_query = Step(
    id="json_filepath",
    prompt="Provide the path to your downloaded faucet JSON file.",
    help="The file should contain the 'mnemonic' and 'secret' fields.",
    validator=[validators.required_field, validators.filepath],
)

password_filename_query = Step(
    id="password_filename",
    prompt="Provide the path to the file with password.",
    help="The file should contain the password in plain text.",
    validator=[validators.required_field, validators.filepath],
)


def get_ledger_url_query(ledgers):
    return Step(
        id="ledger_url",
        prompt="Choose a ledger to get the new derivation from.",
        options=ledgers,
        default=None,
        validator=[validators.required_field, validators.enum_range(ledgers)],
        help="In order to specify new derivation path, you need to specify a ledger to get the derivation from.",
    )


# We define this step as a function since the corresponding step requires
# tezos-node to be running and bootstrapped in order to gather the data
# about the ledger-stored addresses, so it's called right before invoking
# after the node was boostrapped
def get_ledger_derivation_query(ledgers_derivations, node_endpoint, client_dir):
    extra_options = ["Specify derivation path", "Go back"]
    full_ledger_urls = []
    for ledger_url, derivations_paths in ledgers_derivations.items():
        for derivation_path in derivations_paths:
            full_ledger_urls.append(ledger_url + derivation_path)
    return Step(
        id="ledger_derivation",
        prompt="Select a key to import from the ledger.\n"
        "You can choose one of the suggested derivations or provide your own:",
        help="'Specify derivation path' will ask a derivation path from you."
        "'Go back' will return you back to the key type choice.",
        default=None,
        options=[ledger_urls_info(ledgers_derivations, node_endpoint, client_dir)] + extra_options,
        validator=
            [
                validators.required_field,
                validators.enum_range(full_ledger_urls + extra_options),
            ]
        ,
    )


replace_key_options = {
    "no": "Keep the existing key",
    "yes": "Import a new key and replace the existing one",
}

replace_key_query = Step(
    id="replace_key",
    prompt="Would you like to import a new key and replace this one?",
    help="It's possible to proceed with the existing baker key, instead of\n"
    "importing new one.",
    options=replace_key_options,
    validator=validators.enum_range(replace_key_options),
)
