#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2023 Oxhead Alpha
# SPDX-License-Identifier: LicenseRef-MIT-OA

import subprocess
import os
import re
import shutil

octez_version = os.getenv("OCTEZ_VERSION", None)

if not octez_version:
    raise Exception("Environment variable OCTEZ_VERSION is not set.")

subprocess.run(
    [
        "git",
        "clone",
        "--branch",
        octez_version,
        "https://gitlab.com/tezos/tezos.git",
        "--depth",
        "1",
    ]
)
# NOTE: it's important to keep the `tezos/.git` directory here, because the
# git tag is used to set the version in the Octez binaries.

subprocess.run(
    [
        "git",
        "clone",
        "https://github.com/ocaml/opam-repository.git",
        "opam-repository",
    ]
)

opam_repository_tag = (
    subprocess.run(
        ". ./tezos/scripts/version.sh; echo $opam_repository_tag",
        stdout=subprocess.PIPE,
        shell=True,
    )
    .stdout.decode()
    .strip(l)
)

deps = subprocess.run(
    [
        "opam",
        "list",
        "--required-by=./tezos/opam/virtual/octez-deps.opam.locked",
        "--recursive",
        "--depopts" "--columns=name,version",
    ],
    capture_output=True,
).stdout.decode("utf-8").split("\n")

os.chdir("opam-repository")
subprocess.run(["git", "checkout", opam_repository_tag])
subprocess.run(["rm", "-rf", ".git"])
for dep in deps:
    subprocess.run(["opam", "admin", "cache", "add", ".", dep])
