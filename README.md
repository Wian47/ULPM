# Universal Linux Package Manager CLI

A beautiful, all-in-one CLI tool for managing **Flatpak**, **Snap**, and **DNF** applications on Fedora Linux.

## Features
- **Unified Management**: Manage Flatpak, Snap, and DNF apps in one place.
- **Interactive Mode**: Easy-to-use menu system for browsing and managing apps.
- **Search**: Find apps across all repositories with rich formatted tables.
- **Install/Remove**: Manage apps easily.
- **Update**: Update all apps with one command.
- **Beautiful UI**: Powered by `rich` and `typer`.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

**Interactive Mode:**
```bash
python3 main.py
```

**CLI Mode:**
```bash
python3 main.py search <query>
python3 main.py list
python3 main.py install <app_id> --manager <flatpak|snap|dnf>
```
