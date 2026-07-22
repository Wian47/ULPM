import shutil
from typing import Optional


def read_os_release() -> dict:
    data = {}
    try:
        with open("/etc/os-release", "r") as f:
            for line in f:
                line = line.strip()
                if not line or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                data[key] = value.strip('"')
    except FileNotFoundError:
        pass
    return data


def detect_atomic() -> Optional[str]:
    """Returns 'rpm-ostree' or 'transactional-update' if this is an atomic/
    immutable distro (Fedora Silverblue/Kinoite/uCore, openSUSE MicroOS/Aeon),
    where the root filesystem is read-only and packages must be layered via
    a special tool instead of installed directly with dnf/zypper. Returns
    None on a normal, mutable distro."""
    if shutil.which("rpm-ostree"):
        return "rpm-ostree"
    if shutil.which("transactional-update"):
        return "transactional-update"
    return None
