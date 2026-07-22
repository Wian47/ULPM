# Universal Linux Package Manager(ULPM)

[![CI](https://github.com/Wian47/ULPM/actions/workflows/ci.yml/badge.svg)](https://github.com/Wian47/ULPM/actions/workflows/ci.yml)

A beautiful, all-in-one CLI tool for managing **Flatpak**, **Snap**, and **System Packages** (DNF, APT, Pacman, Zypper, APK, XBPS, Portage) on Linux — meant to be the first thing you run on a fresh install, no matter the distro.

## Features
- **Unified Management**: Manage Flatpak, Snap, and native system apps (DNF, APT, Pacman, Zypper, APK, XBPS, Portage) in one place.
- **Self-Bootstrapping**: If Flatpak or Snap aren't preinstalled, ULPM offers to install them for you via your system's native package manager.
- **Smart App Filtering**: Automatically filters system packages to show only user-facing applications (via .desktop files).
- **Interactive Mode**: Easy-to-use menu system for browsing and managing apps.
- **Search**: Find apps across all repositories with rich formatted tables.
- **Install/Remove**: Manage apps easily.
- **Update**: Update all apps with one command.
- **Beautiful UI**: Powered by `rich` and `typer`.
- **Multi-Distro Support**: Automatically detects your package manager.
- **Safety Net**: Every install and system tweak supports `--dry-run` preview and can be reversed with `ulpm undo`.
- **Setup Profiles**: One-click "Developer Workstation," "Gaming Rig," "Minimal Server," and "Privacy Focused" profiles bundling curated apps, tweaks, and security hardening.
- **Security Hardening**: Firewall (ufw/firewalld), fail2ban, and opt-in SSH hardening (double-confirmed to avoid remote lockouts).
- **Driver & Gaming Setup**: Detects NVIDIA GPUs and offers driver install; one-click gaming performance tools (GameMode, MangoHud).
- **Shell Setup**: Optional zsh+starship or fish, set as your default shell.
- **Atomic/Immutable Distro Aware**: Detects Fedora Silverblue/Kinoite and openSUSE MicroOS and routes installs through `rpm-ostree`/`transactional-update` instead of a plain package manager.

## Supported Distros

Tested in CI on Ubuntu, Fedora, Arch Linux, openSUSE Tumbleweed, and Alpine (see the badge above). Package manager support:

| Distro family | Manager | Notes |
|---|---|---|
| Fedora / RHEL | DNF | Auto-detects Silverblue/Kinoite (rpm-ostree) and layers packages accordingly |
| Debian / Ubuntu | APT | |
| Arch / Manjaro | Pacman | Snap isn't auto-installed here (AUR-only; needs a helper like yay/paru) |
| openSUSE | Zypper | Auto-detects MicroOS/Aeon (transactional-update) |
| Alpine | APK | Snap isn't supported (not packaged for musl) |
| Void | XBPS | |
| Gentoo | Portage (emerge) | Slower by nature (source-based); `list` needs `app-portage/portage-utils` installed |

Flatpak and Snap are managed on top of whichever of the above is detected, and ULPM offers to install them itself if they're missing.

## How this compares

ULPM isn't trying to replace tools like [linutil](https://github.com/ChrisTitusTech/linutil) or [omakub](https://github.com/basecamp/omakub) — it has a narrower, specific focus: **be a real cross-distro package manager first**, with setup/tweaks layered on top.

| | ULPM | linutil | omakub |
|---|---|---|---|
| Distro scope | Any (7 native package managers + Flatpak/Snap) | Distro-agnostic | Ubuntu 24.04+ only |
| Core model | Unified package manager (search/install/remove/update across all sources) | Curated setup/config scripts in a TUI | Opinionated one-shot dev environment setup |
| Safety net | `--dry-run` + `undo` on every install/tweak, with automatic backups | Not a core feature | Not applicable (one-shot script) |
| Atomic distro handling | Detects Silverblue/Kinoite/MicroOS and adjusts | — | — |
| Language/runtime | Python (installed via pipx) | Rust (single static binary) | Shell scripts |

## Installation

The one-liner — works on a genuinely fresh install with nothing preinstalled (it bootstraps python3/pip/pipx itself if they're missing):

```bash
curl -fsSL https://raw.githubusercontent.com/Wian47/ULPM/main/install.sh | sh
```

Or, if you already have Python and [pipx](https://pipx.pypa.io/):

```bash
pipx install "git+https://github.com/Wian47/ULPM.git"
```

For local development:

```bash
pip install -e .
```

## Usage

**Interactive Mode:**
```bash
ulpm
```

**CLI Mode:**
```bash
ulpm search <query>
ulpm list
ulpm install <app_id> --manager <flatpak|snap|dnf|apt|pacman|zypper|apk|xbps|portage>
ulpm --dry-run install <app_id>   # preview without applying
ulpm undo                          # reverse the last reversible action
ulpm history                       # see everything ULPM has changed
```
