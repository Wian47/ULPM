# Universal Linux Package Manager(ULPM)

A beautiful, all-in-one CLI tool for managing **Flatpak**, **Snap**, and **System Packages** (DNF, APT, Pacman, Zypper, APK, XBPS, Portage) on Linux.

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
