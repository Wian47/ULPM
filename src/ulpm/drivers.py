import shutil
import subprocess

from rich.console import Console

from .safety import SystemGuard

# Best-effort package names per system manager. NVIDIA driver packaging varies
# a lot by distro (Fedora needs RPM Fusion enabled first, openSUSE needs the
# NVIDIA repo added, etc.) -- this covers the common case and prints guidance
# where it can't be fully automated rather than failing silently.
NVIDIA_PACKAGES = {
    "dnf": "akmod-nvidia",
    "apt": "nvidia-driver",
    "pacman": "nvidia",
    "zypper": "x11-video-nvidiaG06",
}

GAMING_PERF_PACKAGES = {
    "dnf": ["gamemode", "mangohud"],
    "apt": ["gamemode", "mangohud"],
    "pacman": ["gamemode", "mangohud"],
    "zypper": ["gamemode", "mangohud"],
    "apk": ["gamemode"],
}


class DriverManager:
    def __init__(self, console: Console, guard: SystemGuard):
        self.console = console
        self.guard = guard

    def detect_nvidia(self) -> bool:
        if not shutil.which("lspci"):
            return False
        try:
            output = subprocess.run(["lspci"], capture_output=True, text=True, check=False).stdout
            return "nvidia" in output.lower()
        except Exception:
            return False

    def install_nvidia_driver(self, system_mgr) -> bool:
        if not system_mgr:
            self.console.print("[yellow]No system package manager detected; can't install NVIDIA drivers.[/yellow]")
            return False

        pkg = NVIDIA_PACKAGES.get(system_mgr.name.lower())
        if not pkg:
            self.console.print(f"[yellow]No known NVIDIA driver package for {system_mgr.name}. Install manually via your distro's docs.[/yellow]")
            return False

        if system_mgr.name.lower() == "dnf":
            self.console.print("[yellow]Note: akmod-nvidia requires the RPM Fusion repo to already be enabled.[/yellow]")

        return system_mgr.install(pkg)

    def install_gaming_stack(self, system_mgr) -> bool:
        """Installs gamemode/mangohud (gaming performance tools) via the system
        package manager. Steam/Lutris/etc. are handled separately as curated
        Flatpak/Snap apps -- these are libraries, not desktop apps."""
        if not system_mgr:
            self.console.print("[yellow]No system package manager detected; can't install gaming performance tools.[/yellow]")
            return False

        pkgs = GAMING_PERF_PACKAGES.get(system_mgr.name.lower())
        if not pkgs:
            self.console.print(f"[yellow]No known gamemode/mangohud packages for {system_mgr.name}. Skipping.[/yellow]")
            return False

        ok = True
        for pkg in pkgs:
            ok = system_mgr.install(pkg) and ok
        return ok
