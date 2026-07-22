#!/bin/sh
# ULPM bootstrap installer.
#
# Meant to be run on a genuinely fresh Linux install where python3, pip, and
# pipx may not exist yet:
#
#   curl -fsSL https://raw.githubusercontent.com/Wian47/ULPM/main/install.sh | sh
#
# Detects the distro's package manager, installs python3/pip/pipx if missing
# (preferring distro-packaged pipx over `pip install --user pipx`, since
# Debian 12+/Fedora 39+ block unmanaged pip installs by default), installs
# ULPM with pipx, then execs it.

set -eu

REPO_URL="git+https://github.com/Wian47/ULPM.git"

log() { printf '\033[1;34m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$1" >&2; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$1" >&2; exit 1; }

if [ "$(id -u)" = "0" ]; then
    SUDO=""
else
    command -v sudo >/dev/null 2>&1 || die "This installer needs root or sudo. Run as root, or install sudo first."
    SUDO="sudo"
fi

# --- Distro detection -------------------------------------------------------

PKG_FAMILY=""
if [ -r /etc/os-release ]; then
    . /etc/os-release
    for id in ${ID:-} ${ID_LIKE:-}; do
        case "$id" in
            debian|ubuntu) PKG_FAMILY="apt"; break ;;
            fedora|rhel) PKG_FAMILY="dnf"; break ;;
            arch) PKG_FAMILY="pacman"; break ;;
            opensuse*|suse) PKG_FAMILY="zypper"; break ;;
            alpine) PKG_FAMILY="apk"; break ;;
            void) PKG_FAMILY="xbps"; break ;;
            gentoo) PKG_FAMILY="emerge"; break ;;
        esac
    done
fi
[ -n "$PKG_FAMILY" ] || die "Could not detect a supported distro from /etc/os-release."
log "Detected package family: $PKG_FAMILY"

# --- Ensure python3 + pip3 + pipx --------------------------------------------

have() { command -v "$1" >/dev/null 2>&1; }

# Do this before any `have pipx` checks: a user-level pipx from a prior run
# (or installed manually) lives here and isn't on PATH in a bare curl|sh
# session, which would otherwise cause us to needlessly sudo-install it again.
export PATH="$HOME/.local/bin:$PATH"

case "$PKG_FAMILY" in
    apt)
        have python3 || $SUDO apt-get update -y && $SUDO apt-get install -y python3
        have pip3 || $SUDO apt-get install -y python3-pip
        have pipx || $SUDO apt-get install -y pipx || true
        ;;
    dnf)
        have python3 || $SUDO dnf install -y python3
        have pip3 || $SUDO dnf install -y python3-pip
        have pipx || $SUDO dnf install -y pipx || true
        ;;
    pacman)
        have python3 || $SUDO pacman -Sy --noconfirm python
        have pip3 || $SUDO pacman -Sy --noconfirm python-pip
        have pipx || $SUDO pacman -Sy --noconfirm python-pipx || true
        ;;
    zypper)
        have python3 || $SUDO zypper --non-interactive install python3
        have pip3 || $SUDO zypper --non-interactive install python3-pip
        have pipx || $SUDO zypper --non-interactive install python3-pipx || true
        ;;
    apk)
        have python3 || $SUDO apk add python3
        have pip3 || $SUDO apk add py3-pip
        have pipx || $SUDO apk add pipx || true
        ;;
    xbps)
        have python3 || $SUDO xbps-install -y python3
        have pip3 || $SUDO xbps-install -y python3-pip
        have pipx || $SUDO xbps-install -y python3-pipx || true
        ;;
    emerge)
        have python3 || $SUDO emerge --ask=n dev-lang/python
        have pip3 || $SUDO emerge --ask=n dev-python/pip
        have pipx || $SUDO emerge --ask=n dev-python/pipx || true
        ;;
esac

have python3 || die "python3 install failed; please install it manually and re-run."

# Fall back to `pip install --user pipx` only if the distro has no pipx package.
if ! have pipx; then
    log "No distro package for pipx found; falling back to 'pip install --user pipx'."
    python3 -m pip install --user --break-system-packages pipx 2>/dev/null \
        || python3 -m pip install --user pipx \
        || die "Could not install pipx via pip."
fi

have pipx || die "pipx still not on PATH after install; open a new shell and re-run this script."

# --- Install ULPM ------------------------------------------------------------

log "Installing ULPM via pipx..."
pipx install --force "$REPO_URL"

ULPM_BIN="$HOME/.local/bin/ulpm"
[ -x "$ULPM_BIN" ] || die "ULPM installed but $ULPM_BIN not found."

log "Done. Launching ULPM..."
exec "$ULPM_BIN" "$@"
