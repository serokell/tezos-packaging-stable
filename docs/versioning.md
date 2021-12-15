<!--
   - SPDX-FileCopyrightText: 2021 TQ Tezos <https://tqtezos.com/>
   -
   - SPDX-License-Identifier: LicenseRef-MIT-TQ
   -->

# Versioning

`tezos-packaging` provides support for all Octez stable releases and RC candidates.

However, in some cases we provide multiple releases within the same upstream version
because our packages provide additional functionality (e.g. systemd services in Ubuntu
and Fedora packages or brew formulae with launchd services) that may need to be updated
within the single upstream release.

In order to achieve that, our GitHub releases and packages use the following RPM-like versioning scheme:
`<upstream-version>-<release-number>`, e.g. `v11.0-1` for the first `tezos-packaging` release
within the `v11.0` upstream stable release, or `v11.0-rc2-2` for the second `tezos-packaging` release
within the `v11.0-rc2` upstream release candidate.

`<release-number>` is used to reflect the changes in additional packages functionality.

## Github releases

We provide at github releases for stable upstream releases and pre-releases for release candidates.

Github {pre-}releases contain static binaries and brew bottles compiled from the given
upstream source version.

## Ubuntu packages

Ubuntu packages use slightly different versioning scheme, which is used to follow
the [Debian versioning policy](https://www.debian.org/doc/debian-policy/ch-controlfields.html#version):
`<upstream-version>-0ubuntu<release-number>~<ubuntu-version>`, e.g.
`11.0+no-adx-0ubuntu1~focal`, where `focal` is `20.04 LTS`.

We use different PPA repositories for stable and release candidate Ubuntu packages.
You can read more about this in the [doc about Ubuntu packages](./distros/ubuntu.md).

## Fedora packages

We use different Copr projects for stable and release candidate Fedora packages.
You can read more about this in the [doc about Fedora packages](./distros/fedora.md).

## Brew formulae

We use two distinct repository mirrors to provide stable and release candidate brew formulae.
You can read more about this in the [doc about macOS packaging](./distros/macos.md).
