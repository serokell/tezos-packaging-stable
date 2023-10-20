#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2019 TQ Tezos <https://tqtezos.com/>
#
# SPDX-License-Identifier: LicenseRef-MIT-TQ

bot_name="CI bot"

git config --local user.email "hi@serokell.io"
git config --local user.name "$bot_name"
git remote remove auth-origin 2> /dev/null || :
git remote add auth-origin "https://oath2:$GITHUB_PUSH_TOKEN@github.com:serokell/tezos-packaging.git"
git fetch
git checkout -B "$1" --track "origin/$1"

python3 /tezos-packiging/docker/package/scripts/update-binaries-list.py $1

git add --all
git commit --fixup HEAD -m "Updated binaries for $1 release"
git push auth-origin "$our_branch"
