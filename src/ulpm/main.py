import typer
import subprocess
import sys
import shutil
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, Confirm
from typing import Optional, List, Dict
import glob
import json
import os
from importlib import resources

from .tweaks import SystemOptimizer
from .safety import SystemGuard
from .security import SecurityManager
from .drivers import DriverManager
from .shell_setup import ShellSetup

app = typer.Typer(help="Universal Linux Package Manager (ULPM) - A beautiful CLI for managing Flatpak, Snap, and System Packages.")
console = Console()
guard = SystemGuard(console)

# --- Package Manager Abstractions ---

class PackageManager:
    name: str
    color: str

    def search(self, query: str) -> List[Dict[str, str]]:
        return []

    def list_installed(self) -> List[Dict[str, str]]:
        return []

    def install(self, app_id: str):
        pass

    def remove(self, app_id: str):
        pass

    def update(self):
        pass
    
    def info(self, app_id: str) -> str:
        return ""

class FlatpakManager(PackageManager):
    name = "Flatpak"
    color = "blue"

    def __init__(self):
        self.available = shutil.which("flatpak") is not None

    def _run(self, args: List[str], capture: bool = True) -> str:
        if not self.available:
            return ""
        cmd = ["flatpak"] + args
        try:
            if capture:
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                return result.stdout
            else:
                subprocess.run(cmd, check=True)
                return ""
        except (subprocess.CalledProcessError, FileNotFoundError):
            return ""

    def ensure_flathub(self):
        if not self.available:
            return
        # Check if flathub exists
        output = self._run(["remote-list"], capture=True)
        if "flathub" not in output:
            console.print("[blue]Adding Flathub remote...[/blue]")
            self._run(["remote-add", "--if-not-exists", "flathub", "https://dl.flathub.org/repo/flathub.flatpakrepo"], capture=False)

    def search(self, query: str) -> List[Dict[str, str]]:
        self.ensure_flathub()
        output = self._run(["search", query, "--columns=name,description,application,version,remotes"])
        results = []
        if output:
            for line in output.strip().split('\n'):
                parts = line.split('\t')
                if len(parts) >= 5:
                    results.append({
                        "name": parts[0],
                        "description": parts[1],
                        "id": parts[2],
                        "version": parts[3],
                        "source": "flathub" # Simplified
                    })
        return results

    def list_installed(self) -> List[Dict[str, str]]:
        output = self._run(["list", "--app", "--columns=name,application,version,origin"])
        results = []
        if output:
            for line in output.strip().split('\n'):
                parts = line.split('\t')
                if len(parts) >= 4:
                    results.append({
                        "name": parts[0],
                        "id": parts[1],
                        "version": parts[2],
                        "source": parts[3]
                    })
        return results

    def install(self, app_id: str) -> bool:
        if not self.available:
            console.print("[red]Flatpak isn't installed on this system.[/red]")
            return False
        self.ensure_flathub()
        if guard.run(["flatpak", "install", "-y", "flathub", app_id], f"Installing {app_id} (Flatpak)",
                      reversible=True, reverse_cmd=["flatpak", "uninstall", "-y", app_id]):
            return True
        # Fallback: try without remote specifier if flathub fails (unlikely but safe)
        return guard.run(["flatpak", "install", "-y", app_id], f"Installing {app_id} (Flatpak)",
                          reversible=True, reverse_cmd=["flatpak", "uninstall", "-y", app_id])

    def remove(self, app_id: str):
        if not self.available:
            console.print("[red]Flatpak isn't installed on this system.[/red]")
            return
        guard.run(["flatpak", "uninstall", "-y", app_id], f"Removing {app_id} (Flatpak)")

    def update(self):
        if not self.available:
            console.print("[red]Flatpak isn't installed on this system.[/red]")
            return
        guard.run(["flatpak", "update", "-y"], "Updating Flatpak apps")

    def info(self, app_id: str) -> str:
        return self._run(["info", app_id])

class SnapManager(PackageManager):
    name = "Snap"
    color = "green"

    def __init__(self):
        self.available = shutil.which("snap") is not None

    def _run(self, args: List[str], capture: bool = True) -> str:
        if not self.available:
            return ""
        cmd = ["snap"] + args
        try:
            if capture:
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                return result.stdout
            else:
                subprocess.run(cmd, check=True)
                return ""
        except subprocess.CalledProcessError:
            return ""

    def search(self, query: str) -> List[Dict[str, str]]:
        if not self.available: return []
        # Snap search output is fixed width-ish, but usually separated by spaces.
        # Name, Version, Publisher, Notes, Summary
        # We can't easily parse columns, but let's try basic split.
        # Warning: descriptions can have spaces.
        # Better approach: snap search <query> returns a table.
        # We might just display it as is or try to parse.
        # For robustness in this MVP, we'll try to parse the first few columns.
        output = self._run(["search", query])
        results = []
        if output:
            lines = output.strip().split('\n')
            if len(lines) > 1:
                # Skip header
                for line in lines[1:]:
                    parts = line.split()
                    if len(parts) >= 5:
                        # Heuristic: Name is col 0, Version col 1, Publisher col 2
                        # Summary is the rest.
                        results.append({
                            "name": parts[0],
                            "description": " ".join(parts[4:]),
                            "id": parts[0], # Snap ID is the name
                            "version": parts[1],
                            "source": "snapcraft"
                        })
        return results

    def list_installed(self) -> List[Dict[str, str]]:
        if not self.available: return []
        output = self._run(["list"])
        results = []
        if output:
            lines = output.strip().split('\n')
            if len(lines) > 1:
                for line in lines[1:]:
                    parts = line.split()
                    if len(parts) >= 3:
                        results.append({
                            "name": parts[0],
                            "id": parts[0],
                            "version": parts[1],
                            "source": "snap"
                        })
        return results

    def install(self, app_id: str) -> bool:
        console.print("[yellow]Note: Snap installation may require sudo password.[/yellow]")
        return guard.run(["sudo", "snap", "install", app_id], f"Installing {app_id} (Snap)",
                          reversible=True, reverse_cmd=["sudo", "snap", "remove", app_id])

    def remove(self, app_id: str):
        console.print("[yellow]Note: Snap removal may require sudo password.[/yellow]")
        guard.run(["sudo", "snap", "remove", app_id], f"Removing {app_id} (Snap)")

    def update(self):
        console.print("[yellow]Note: Snap refresh may require sudo password.[/yellow]")
        guard.run(["sudo", "snap", "refresh"], "Updating Snap apps")

    def info(self, app_id: str) -> str:
        return self._run(["info", app_id])

class DnfManager(PackageManager):
    name = "DNF"
    color = "yellow"
    flatpak_pkg = "flatpak"
    snap_pkg = "snapd"

    def __init__(self):
        self.available = shutil.which("dnf") is not None

    def _run(self, args: List[str], capture: bool = True) -> str:
        if not self.available:
            return ""
        cmd = ["dnf"] + args
        try:
            if capture:
                # dnf can be slow, maybe we shouldn't block too long, but for CLI it's fine.
                result = subprocess.run(cmd, capture_output=True, text=True, check=False) # check=False because dnf return codes vary
                return result.stdout
            else:
                subprocess.run(cmd, check=False)
                return ""
        except Exception:
            return ""

    def search(self, query: str) -> List[Dict[str, str]]:
        if not self.available: return []
        # dnf search -q <query>
        output = self._run(["search", "-q", query])
        results = []
        if output:
            lines = output.strip().split('\n')
            for line in lines:
                # Filter out metadata lines from dnf search
                if "Matched:" in line or "Match:" in line or line.startswith("="):
                    continue
                
                # DNF output often looks like: " package.arch   Summary text"
                # It might use tabs or multiple spaces.
                parts = line.strip().split(None, 1) # Split on first whitespace chunk
                if len(parts) >= 2:
                    name_part = parts[0].strip()
                    summary = parts[1].strip()
                    
                    # Skip if it looks like a header or metadata
                    if "matched" in name_part.lower() or "match" in name_part.lower():
                        continue
                    
                    # Package names shouldn't have spaces (already handled by split(None, 1) but good to check if parsing failed)
                    
                    # clean name (remove .x86_64 etc)
                    name = name_part.split('.')[0] 
                    results.append({
                        "name": name,
                        "description": summary,
                        "id": name,
                        "version": "repo", 
                        "source": "fedora"
                    })
        return results

    def list_installed(self) -> List[Dict[str, str]]:
        # Filter for apps with .desktop files in /usr/share/applications
        desktop_files = glob.glob("/usr/share/applications/*.desktop")
        if not desktop_files:
            return []

        # rpm -qf --qf "%{NAME}\t%{VERSION}\t%{SUMMARY}\n" <files>
        # We'll process in chunks to avoid command line length limits if necessary, 
        # but for typical desktop counts (~200-500), it should be fine.
        cmd = ["rpm", "-qf", "--qf", "%{NAME}\t%{VERSION}\t%{SUMMARY}\n"] + desktop_files
        
        try:
            # Suppress stderr because some .desktop files might not belong to any package
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            output = result.stdout
        except Exception:
            return []

        results = []
        seen_ids = set()
        
        if output:
            for line in output.strip().split('\n'):
                parts = line.split('\t')
                if len(parts) >= 3:
                    name = parts[0]
                    if name in seen_ids:
                        continue
                    seen_ids.add(name)
                    
                    results.append({
                        "name": name,
                        "id": name,
                        "version": parts[1],
                        "description": parts[2],
                        "source": "dnf"
                    })
        return results 

    def install(self, app_id: str) -> bool:
        console.print("[yellow]Note: DNF installation requires sudo.[/yellow]")
        return guard.run(["sudo", "dnf", "install", "-y", app_id], f"Installing {app_id} (DNF)",
                          reversible=True, reverse_cmd=["sudo", "dnf", "remove", "-y", app_id])

    def remove(self, app_id: str):
        console.print("[yellow]Note: DNF removal requires sudo.[/yellow]")
        guard.run(["sudo", "dnf", "remove", "-y", app_id], f"Removing {app_id} (DNF)")

    def update(self):
        console.print("[yellow]Note: DNF update requires sudo.[/yellow]")
        guard.run(["sudo", "dnf", "update", "-y"], "Updating DNF packages")

    def info(self, app_id: str) -> str:
        return self._run(["info", app_id])

class AptManager(PackageManager):
    name = "APT"
    color = "red"
    flatpak_pkg = "flatpak"
    snap_pkg = "snapd"

    def __init__(self):
        self.available = shutil.which("apt") is not None

    def _run(self, args: List[str], capture: bool = True) -> str:
        if not self.available:
            return ""
        cmd = ["apt"] + args
        try:
            if capture:
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                return result.stdout
            else:
                subprocess.run(cmd, check=False)
                return ""
        except Exception:
            return ""

    def search(self, query: str) -> List[Dict[str, str]]:
        if not self.available: return []
        # apt search <query>
        output = self._run(["search", query])
        results = []
        if output:
            lines = output.strip().split('\n')
            for line in lines:
                if "/" in line and "now" not in line: # Basic filtering for package lines
                     parts = line.split('/')
                     if len(parts) > 1:
                         name = parts[0].strip()
                         # Description is usually on the next line or after ' - '
                         # apt search output is tricky to parse perfectly without -F or similar, 
                         # but let's try a simple split if it exists on same line
                         description = "System Package"
                         if " - " in line:
                             description = line.split(" - ", 1)[1].strip()
                         
                         results.append({
                            "name": name,
                            "description": description,
                            "id": name,
                            "version": "repo",
                            "source": "apt"
                         })
        return results

    def list_installed(self) -> List[Dict[str, str]]:
        desktop_files = glob.glob("/usr/share/applications/*.desktop")
        if not desktop_files: return []

        # 1. Get packages owning these files
        # dpkg -S <files>
        cmd = ["dpkg", "-S"] + desktop_files
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            output = result.stdout
        except Exception:
            return []
            
        packages = set()
        if output:
            for line in output.strip().split('\n'):
                # Output: package: /path/to/file
                if ": " in line:
                    pkg = line.split(": ")[0]
                    # Handle multi-arch (e.g., package:amd64)
                    pkg = pkg.split(':')[0] 
                    packages.add(pkg)
        
        if not packages:
            return []

        # 2. Get details for these packages
        # dpkg-query -W -f='${binary:Package}\t${Version}\n' <packages>
        cmd_details = ["dpkg-query", "-W", "-f=${binary:Package}\t${Version}\n"] + list(packages)
        try:
            result = subprocess.run(cmd_details, capture_output=True, text=True, check=False)
            output = result.stdout
        except Exception:
            return []

        results = []
        if output:
            for line in output.strip().split('\n'):
                parts = line.split('\t')
                if len(parts) >= 2:
                    results.append({
                        "name": parts[0],
                        "id": parts[0],
                        "version": parts[1],
                        "source": "apt"
                    })
        return results

    def install(self, app_id: str) -> bool:
        console.print("[yellow]Note: APT installation requires sudo.[/yellow]")
        return guard.run(["sudo", "apt", "install", "-y", app_id], f"Installing {app_id} (APT)",
                          reversible=True, reverse_cmd=["sudo", "apt", "remove", "-y", app_id])

    def remove(self, app_id: str):
        console.print("[yellow]Note: APT removal requires sudo.[/yellow]")
        guard.run(["sudo", "apt", "remove", "-y", app_id], f"Removing {app_id} (APT)")

    def update(self):
        console.print("[yellow]Note: APT update requires sudo.[/yellow]")
        guard.run(["sudo", "apt", "update"], "Updating APT package index")
        guard.run(["sudo", "apt", "upgrade", "-y"], "Upgrading APT packages")

    def info(self, app_id: str) -> str:
        return self._run(["show", app_id])

class PacmanManager(PackageManager):
    name = "Pacman"
    color = "yellow"
    flatpak_pkg = "flatpak"
    snap_pkg = None  # snapd is AUR-only on Arch; not installable via pacman directly

    def __init__(self):
        self.available = shutil.which("pacman") is not None

    def _run(self, args: List[str], capture: bool = True) -> str:
        if not self.available:
            return ""
        cmd = ["pacman"] + args
        try:
            if capture:
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                return result.stdout
            else:
                subprocess.run(cmd, check=False)
                return ""
        except Exception:
            return ""

    def search(self, query: str) -> List[Dict[str, str]]:
        if not self.available: return []
        # pacman -Ss <query>
        output = self._run(["-Ss", query])
        results = []
        if output:
            lines = output.strip().split('\n')
            # Output format:
            # repo/name version [installed]
            #     Description
            current_pkg = {}
            for line in lines:
                if not line.startswith("    "):
                    parts = line.split(' ')
                    if len(parts) >= 2:
                        name_part = parts[0] # repo/name
                        name = name_part.split('/')[1] if '/' in name_part else name_part
                        version = parts[1]
                        current_pkg = {
                            "name": name,
                            "id": name,
                            "version": version,
                            "source": "arch"
                        }
                else:
                    if current_pkg:
                        current_pkg["description"] = line.strip()
                        results.append(current_pkg)
                        current_pkg = {}
        return results

    def list_installed(self) -> List[Dict[str, str]]:
        if not self.available: return []
        
        desktop_files = glob.glob("/usr/share/applications/*.desktop")
        if not desktop_files: return []

        # pacman -Qo <files>
        cmd = ["pacman", "-Qo"] + desktop_files
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            output = result.stdout
        except Exception:
            return []
            
        results = []
        seen_ids = set()
        
        if output:
            lines = output.strip().split('\n')
            for line in lines:
                # Output: /path/to/file is owned by package version
                if " is owned by " in line:
                    parts = line.split(" is owned by ")
                    if len(parts) == 2:
                        pkg_info = parts[1].split()
                        if len(pkg_info) >= 2:
                            name = pkg_info[0]
                            version = pkg_info[1]
                            
                            if name in seen_ids:
                                continue
                            seen_ids.add(name)
                            
                            results.append({
                                "name": name,
                                "id": name,
                                "version": version,
                                "source": "pacman"
                            })
        return results

    def install(self, app_id: str) -> bool:
        console.print("[yellow]Note: Pacman installation requires sudo.[/yellow]")
        return guard.run(["sudo", "pacman", "-S", "--noconfirm", app_id], f"Installing {app_id} (Pacman)",
                          reversible=True, reverse_cmd=["sudo", "pacman", "-R", "--noconfirm", app_id])

    def remove(self, app_id: str):
        console.print("[yellow]Note: Pacman removal requires sudo.[/yellow]")
        guard.run(["sudo", "pacman", "-R", "--noconfirm", app_id], f"Removing {app_id} (Pacman)")

    def update(self):
        console.print("[yellow]Note: Pacman update requires sudo.[/yellow]")
        guard.run(["sudo", "pacman", "-Syu", "--noconfirm"], "Updating Pacman packages")

    def info(self, app_id: str) -> str:
        return self._run(["-Si", app_id])

class ZypperManager(PackageManager):
    name = "Zypper"
    color = "magenta"
    flatpak_pkg = "flatpak"
    snap_pkg = "snapd"

    def __init__(self):
        self.available = shutil.which("zypper") is not None

    def _run(self, args: List[str], capture: bool = True) -> str:
        if not self.available:
            return ""
        cmd = ["zypper", "--non-interactive"] + args
        try:
            if capture:
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                return result.stdout
            else:
                subprocess.run(cmd, check=False)
                return ""
        except Exception:
            return ""

    def search(self, query: str) -> List[Dict[str, str]]:
        if not self.available: return []
        output = self._run(["search", query])
        results = []
        if output:
            lines = output.strip().split('\n')
            started = False
            for line in lines:
                if line.strip().startswith("--"):
                    started = True
                    continue
                if not started or "|" not in line:
                    continue
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 4:
                    name = parts[1]
                    summary = parts[2]
                    if not name or name.lower() == "name":
                        continue
                    results.append({
                        "name": name,
                        "description": summary,
                        "id": name,
                        "version": "repo",
                        "source": "zypper"
                    })
        return results

    def list_installed(self) -> List[Dict[str, str]]:
        desktop_files = glob.glob("/usr/share/applications/*.desktop")
        if not desktop_files: return []

        cmd = ["rpm", "-qf", "--qf", "%{NAME}\t%{VERSION}\t%{SUMMARY}\n"] + desktop_files
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            output = result.stdout
        except Exception:
            return []

        results = []
        seen_ids = set()
        if output:
            for line in output.strip().split('\n'):
                parts = line.split('\t')
                if len(parts) >= 3:
                    name = parts[0]
                    if name in seen_ids:
                        continue
                    seen_ids.add(name)
                    results.append({
                        "name": name,
                        "id": name,
                        "version": parts[1],
                        "description": parts[2],
                        "source": "zypper"
                    })
        return results

    def install(self, app_id: str) -> bool:
        console.print("[yellow]Note: Zypper installation requires sudo.[/yellow]")
        return guard.run(["sudo", "zypper", "--non-interactive", "install", app_id], f"Installing {app_id} (Zypper)",
                          reversible=True, reverse_cmd=["sudo", "zypper", "--non-interactive", "remove", app_id])

    def remove(self, app_id: str):
        console.print("[yellow]Note: Zypper removal requires sudo.[/yellow]")
        guard.run(["sudo", "zypper", "--non-interactive", "remove", app_id], f"Removing {app_id} (Zypper)")

    def update(self):
        console.print("[yellow]Note: Zypper update requires sudo.[/yellow]")
        guard.run(["sudo", "zypper", "--non-interactive", "update"], "Updating Zypper packages")

    def info(self, app_id: str) -> str:
        return self._run(["info", app_id])

class ApkManager(PackageManager):
    name = "APK"
    color = "cyan"
    flatpak_pkg = "flatpak"
    snap_pkg = None  # snapd isn't packaged for Alpine's musl base

    def __init__(self):
        self.available = shutil.which("apk") is not None

    def _run(self, args: List[str], capture: bool = True) -> str:
        if not self.available:
            return ""
        cmd = ["apk"] + args
        try:
            if capture:
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                return result.stdout
            else:
                subprocess.run(cmd, check=False)
                return ""
        except Exception:
            return ""

    def search(self, query: str) -> List[Dict[str, str]]:
        if not self.available: return []
        output = self._run(["search", "-v", query])
        results = []
        if output:
            for line in output.strip().split('\n'):
                line = line.strip()
                if not line:
                    continue
                parts = line.split(' - ', 1)
                pkg = parts[0].strip()
                description = parts[1].strip() if len(parts) > 1 else "Alpine Package"
                # pkg looks like name-version-r<release>; strip the trailing version/release
                segments = pkg.rsplit('-', 2)
                name = segments[0] if len(segments) == 3 else pkg
                results.append({
                    "name": name,
                    "description": description,
                    "id": name,
                    "version": "repo",
                    "source": "alpine"
                })
        return results

    def list_installed(self) -> List[Dict[str, str]]:
        if not self.available: return []
        desktop_files = glob.glob("/usr/share/applications/*.desktop")
        if not desktop_files: return []

        cmd = ["apk", "info", "--who-owns"] + desktop_files
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            output = result.stdout
        except Exception:
            return []

        results = []
        seen_ids = set()
        if output:
            for line in output.strip().split('\n'):
                if " is owned by " in line:
                    pkg = line.split(" is owned by ")[1].strip()
                    segments = pkg.rsplit('-', 2)
                    name = segments[0] if len(segments) == 3 else pkg
                    if name in seen_ids:
                        continue
                    seen_ids.add(name)
                    results.append({
                        "name": name,
                        "id": name,
                        "version": segments[1] if len(segments) == 3 else "",
                        "source": "alpine"
                    })
        return results

    def install(self, app_id: str) -> bool:
        console.print("[yellow]Note: APK installation requires sudo.[/yellow]")
        return guard.run(["sudo", "apk", "add", app_id], f"Installing {app_id} (APK)",
                          reversible=True, reverse_cmd=["sudo", "apk", "del", app_id])

    def remove(self, app_id: str):
        console.print("[yellow]Note: APK removal requires sudo.[/yellow]")
        guard.run(["sudo", "apk", "del", app_id], f"Removing {app_id} (APK)")

    def update(self):
        console.print("[yellow]Note: APK update requires sudo.[/yellow]")
        guard.run(["sudo", "apk", "update"], "Updating APK package index")
        guard.run(["sudo", "apk", "upgrade"], "Upgrading APK packages")

    def info(self, app_id: str) -> str:
        return self._run(["info", app_id])

class XbpsManager(PackageManager):
    name = "XBPS"
    color = "bright_blue"
    flatpak_pkg = "flatpak"
    snap_pkg = None  # not officially packaged for Void

    def __init__(self):
        self.available = shutil.which("xbps-query") is not None

    def _run(self, cmd: List[str], capture: bool = True) -> str:
        try:
            if capture:
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                return result.stdout
            else:
                subprocess.run(cmd, check=False)
                return ""
        except Exception:
            return ""

    def search(self, query: str) -> List[Dict[str, str]]:
        if not self.available: return []
        output = self._run(["xbps-query", "-Rs", query])
        results = []
        if output:
            for line in output.strip().split('\n'):
                line = line.strip()
                if not line.startswith('['):
                    continue
                rest = line[4:].strip()  # drop "[*] " / "[-] " state marker
                parts = rest.split(None, 1)
                if not parts:
                    continue
                pkgver = parts[0]
                description = parts[1] if len(parts) > 1 else ""
                name = pkgver.rsplit('-', 1)[0] if '-' in pkgver else pkgver
                results.append({
                    "name": name,
                    "description": description,
                    "id": name,
                    "version": "repo",
                    "source": "void"
                })
        return results

    def list_installed(self) -> List[Dict[str, str]]:
        if not self.available: return []
        desktop_files = glob.glob("/usr/share/applications/*.desktop")
        if not desktop_files: return []

        cmd = ["xbps-query", "-o"] + desktop_files
        output = self._run(cmd)

        results = []
        seen_ids = set()
        if output:
            for line in output.strip().split('\n'):
                if ':' not in line:
                    continue
                pkgver = line.split(':', 1)[0].strip()
                name = pkgver.rsplit('-', 1)[0] if '-' in pkgver else pkgver
                if name in seen_ids:
                    continue
                seen_ids.add(name)
                results.append({
                    "name": name,
                    "id": name,
                    "version": "",
                    "source": "void"
                })
        return results

    def install(self, app_id: str) -> bool:
        console.print("[yellow]Note: XBPS installation requires sudo.[/yellow]")
        return guard.run(["sudo", "xbps-install", "-y", app_id], f"Installing {app_id} (XBPS)",
                          reversible=True, reverse_cmd=["sudo", "xbps-remove", "-y", app_id])

    def remove(self, app_id: str):
        console.print("[yellow]Note: XBPS removal requires sudo.[/yellow]")
        guard.run(["sudo", "xbps-remove", "-y", app_id], f"Removing {app_id} (XBPS)")

    def update(self):
        console.print("[yellow]Note: XBPS update requires sudo.[/yellow]")
        guard.run(["sudo", "xbps-install", "-Su", "-y"], "Updating XBPS packages")

    def info(self, app_id: str) -> str:
        return self._run(["xbps-query", "-R", app_id])

class EmergeManager(PackageManager):
    name = "Portage"
    color = "purple"
    flatpak_pkg = "sys-apps/flatpak"
    snap_pkg = None  # snap isn't part of the standard Gentoo/Portage workflow

    def __init__(self):
        self.available = shutil.which("emerge") is not None

    def _run(self, cmd: List[str], capture: bool = True) -> str:
        try:
            if capture:
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                return result.stdout
            else:
                subprocess.run(cmd, check=False)
                return ""
        except Exception:
            return ""

    def search(self, query: str) -> List[Dict[str, str]]:
        if not self.available: return []
        console.print("[dim]Searching the Portage tree can take a while on Gentoo...[/dim]")
        output = self._run(["emerge", "--search", query])
        results = []
        if output:
            current_name = None
            for line in output.split('\n'):
                if line.startswith("* "):
                    current_name = line[2:].strip()
                elif "Description:" in line and current_name:
                    description = line.split("Description:", 1)[1].strip()
                    results.append({
                        "name": current_name.split('/')[-1],
                        "description": description,
                        "id": current_name,
                        "version": "repo",
                        "source": "gentoo"
                    })
                    current_name = None
        return results

    def list_installed(self) -> List[Dict[str, str]]:
        if not self.available or not shutil.which("qfile"): return []
        desktop_files = glob.glob("/usr/share/applications/*.desktop")
        if not desktop_files: return []

        output = self._run(["qfile", "-qC"] + desktop_files)
        results = []
        seen_ids = set()
        if output:
            for line in output.strip().split('\n'):
                atom = line.strip()
                if not atom:
                    continue
                name = atom.rsplit('-', 1)[0] if '-' in atom else atom
                if name in seen_ids:
                    continue
                seen_ids.add(name)
                results.append({
                    "name": name.split('/')[-1],
                    "id": name,
                    "version": "",
                    "source": "gentoo"
                })
        return results

    def install(self, app_id: str) -> bool:
        console.print("[yellow]Note: Portage installation requires sudo and may take a long time (source compilation).[/yellow]")
        return guard.run(["sudo", "emerge", "--ask=n", app_id], f"Installing {app_id} (Portage)",
                          reversible=True, reverse_cmd=["sudo", "emerge", "--ask=n", "--unmerge", app_id])

    def remove(self, app_id: str):
        console.print("[yellow]Note: Portage removal requires sudo.[/yellow]")
        guard.run(["sudo", "emerge", "--ask=n", "--unmerge", app_id], f"Removing {app_id} (Portage)")

    def update(self):
        console.print("[yellow]Note: Portage update requires sudo and may take a long time.[/yellow]")
        guard.run(["sudo", "emerge", "--ask=n", "--update", "--deep", "--newuse", "@world"], "Updating Portage/world")

    def info(self, app_id: str) -> str:
        return self._run(["emerge", "--pretend", "--verbose", app_id])

# Initialize Managers
managers = [FlatpakManager(), SnapManager()]

# Detect System Package Manager
if shutil.which("dnf"):
    managers.append(DnfManager())
elif shutil.which("apt"):
    managers.append(AptManager())
elif shutil.which("pacman"):
    managers.append(PacmanManager())
elif shutil.which("zypper"):
    managers.append(ZypperManager())
elif shutil.which("apk"):
    managers.append(ApkManager())
elif shutil.which("xbps-query"):
    managers.append(XbpsManager())
elif shutil.which("emerge"):
    managers.append(EmergeManager())

# --- Curated Apps Data ---



def load_curated_apps():
    try:
        data = resources.files("ulpm").joinpath("apps.json").read_text()
        return json.loads(data)
    except (FileNotFoundError, ModuleNotFoundError):
        return {}

def load_profiles():
    try:
        data = resources.files("ulpm").joinpath("profiles.json").read_text()
        return json.loads(data)
    except (FileNotFoundError, ModuleNotFoundError):
        return {}

CURATED_APPS = load_curated_apps()
PROFILES = load_profiles()

def install_curated_app(app_data: dict) -> bool:
    """Tries Flatpak first, then Snap, for a curated app entry. Shared by the
    curated-app browser and setup profiles so both stay in sync."""
    name = app_data['name']

    flatpak_mgr = next((m for m in managers if isinstance(m, FlatpakManager)), None)
    if flatpak_mgr and 'flatpak' in app_data:
        console.print(f"Installing [cyan]{name}[/cyan] via Flatpak...")
        if flatpak_mgr.install(app_data['flatpak']):
            return True

    snap_mgr = next((m for m in managers if isinstance(m, SnapManager)), None)
    if snap_mgr and 'snap' in app_data:
        console.print(f"Installing [cyan]{name}[/cyan] via Snap...")
        if snap_mgr.install(app_data['snap']):
            return True

    console.print(f"[red]Could not install {name}. Check logs or try another manager.[/red]")
    return False

def bootstrap_app_stores():
    """On a fresh box, Flatpak/Snap usually aren't preinstalled. Offer to install
    them via whatever system package manager was detected, so the very first run
    of ULPM can bootstrap a working app ecosystem instead of assuming one exists."""
    system_mgr = managers[2] if len(managers) > 2 else None
    flatpak_mgr = next((m for m in managers if isinstance(m, FlatpakManager)), None)
    snap_mgr = next((m for m in managers if isinstance(m, SnapManager)), None)

    if flatpak_mgr and not flatpak_mgr.available:
        pkg = getattr(system_mgr, "flatpak_pkg", None) if system_mgr else None
        if pkg:
            if Confirm.ask(f"[yellow]Flatpak isn't installed. Install it now via {system_mgr.name}?[/yellow]"):
                if system_mgr.install(pkg):
                    flatpak_mgr.available = True
                    console.print("[green]Flatpak installed.[/green]")
                else:
                    console.print("[red]Flatpak install failed. You can install it manually later.[/red]")
        else:
            console.print("[dim]Flatpak isn't installed and ULPM doesn't know how to install it on this system.[/dim]")

    if snap_mgr and not snap_mgr.available:
        pkg = getattr(system_mgr, "snap_pkg", None) if system_mgr else None
        if pkg is None and system_mgr is not None:
            console.print(f"[dim]Snap isn't installed. {system_mgr.name} doesn't support installing it directly (needs a helper like an AUR helper on Arch, or isn't packaged for this distro); skipping auto-install.[/dim]")
        elif pkg:
            if Confirm.ask(f"[yellow]Snap isn't installed. Install it now via {system_mgr.name}?[/yellow]"):
                if system_mgr.install(pkg):
                    snap_mgr.available = True
                    console.print("[green]snapd installed. You may need to log out/in or reboot before snap works.[/green]")
                else:
                    console.print("[red]snapd install failed. You can install it manually later.[/red]")

# --- Interactive Functions ---

def interactive_search():
    while True:
        console.clear()
        console.print(Panel("[bold cyan]Interactive Search (Flatpak, Snap, & DNF)[/bold cyan]", border_style="blue"))
        query = Prompt.ask("Enter search query (or 'b' to back)")
        if query.lower() == 'b':
            break
        
        all_results = []
        with console.status(f"[bold green]Searching for '{query}'...[/bold green]", spinner="dots"):
            for mgr in managers:
                results = mgr.search(query)
                for r in results:
                    r['manager'] = mgr
                all_results.extend(results)

        if not all_results:
            console.print(f"[yellow]No results found for '{query}'.[/yellow]")
            Prompt.ask("Press Enter to continue")
            continue

        table = Table(title=f"Search Results for '{query}'", show_header=True, header_style="bold magenta")
        table.add_column("#", style="dim")
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Type", style="bold")
        table.add_column("Description")
        table.add_column("Version", style="green")
        
        for idx, r in enumerate(all_results, 1):
            mgr_style = r['manager'].color
            table.add_row(
                str(idx), 
                r['name'], 
                f"[{mgr_style}]{r['manager'].name}[/{mgr_style}]", 
                r['description'], 
                r['version']
            )

        console.print(table)
        
        choice = Prompt.ask("Enter # to install, 's' to search again, or 'b' to back")
        if choice.lower() == 'b':
            break
        elif choice.lower() == 's':
            continue
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(all_results):
                target = all_results[idx]
                mgr = target['manager']
                app_id = target['id']
                if Confirm.ask(f"Install [bold cyan]{app_id}[/bold cyan] via [{mgr.color}]{mgr.name}[/{mgr.color}]?"):
                    mgr.install(app_id)
                    Prompt.ask("Press Enter to continue")
            else:
                console.print("[red]Invalid selection.[/red]")
                Prompt.ask("Press Enter to continue")

def interactive_list():
    while True:
        console.clear()
        all_apps = []
        with console.status("[bold green]Fetching installed apps...[/bold green]"):
            for mgr in managers:
                apps = mgr.list_installed()
                for a in apps:
                    a['manager'] = mgr
                all_apps.extend(apps)
        
        if not all_apps:
            console.print("[yellow]No apps installed.[/yellow]")
            Prompt.ask("Press Enter to back")
            break

        table = Table(title="Installed Applications", show_header=True, header_style="bold magenta")
        table.add_column("#", style="dim")
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Type", style="bold")
        table.add_column("App ID", style="dim")
        table.add_column("Version", style="green")

        for idx, r in enumerate(all_apps, 1):
            mgr_style = r['manager'].color
            table.add_row(
                str(idx), 
                r['name'], 
                f"[{mgr_style}]{r['manager'].name}[/{mgr_style}]", 
                r['id'], 
                r['version']
            )

        console.print(table)
        
        choice = Prompt.ask("Enter # to manage, 'u' to update all, or 'b' to back")
        if choice.lower() == 'b':
            break
        elif choice.lower() == 'u':
            update()
            Prompt.ask("Press Enter to continue")
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(all_apps):
                target = all_apps[idx]
                mgr = target['manager']
                app_id = target['id']
                action = Prompt.ask(f"Manage {app_id} ({mgr.name})", choices=["info", "remove", "back"], default="info")
                if action == "remove":
                    mgr.remove(app_id)
                elif action == "info":
                    info_text = mgr.info(app_id)
                    console.print(Panel(info_text, title=f"Info: {app_id}", border_style=mgr.color))
                Prompt.ask("Press Enter to continue")

def interactive_curated():
    selected_apps = set() # Stores (category, index) tuples
    
    while True:
        console.clear()
        console.print(Panel("[bold green]Curated App Installer[/bold green]", subtitle="Select apps to install"))
        
        # Flatten list for display
        display_list = []
        
        table = Table(show_header=True, header_style="bold magenta", box=None)
        table.add_column("Sel", style="bold yellow", width=4)
        table.add_column("#", style="dim", width=4)
        table.add_column("Category", style="cyan")
        table.add_column("Name", style="bold white")
        table.add_column("Description")
        
        current_idx = 1
        for cat, apps in CURATED_APPS.items():
            table.add_section()
            for i, app_data in enumerate(apps):
                is_selected = (cat, i) in selected_apps
                sel_mark = "[green][x][/green]" if is_selected else "[dim][ ][/dim]"
                
                table.add_row(
                    sel_mark,
                    str(current_idx),
                    cat if i == 0 else "", 
                    app_data['name'],
                    app_data['desc']
                )
                display_list.append((cat, i))
                current_idx += 1
        
        console.print(table)
        
        console.print("\n[bold]Controls:[/bold]")
        console.print("  [cyan]<number>[/cyan]   : Toggle specific app (e.g., '1')")
        console.print("  [cyan]<range>[/cyan]    : Toggle range (e.g., '1-5')")
        console.print("  [cyan]<list>[/cyan]     : Toggle multiple (e.g., '1,3,5-7')")
        console.print("  [green]i[/green]          : Install selected")
        console.print("  [red]b[/red]          : Back")
        
        choice = Prompt.ask("Selection")
        
        if choice.lower() == 'b':
            break
        elif choice.lower() == 'i':
            if not selected_apps:
                console.print("[yellow]No apps selected.[/yellow]")
                Prompt.ask("Press Enter to continue")
                continue
            
            # Install Logic
            console.clear()
            console.print(Panel(f"[bold green]Installing {len(selected_apps)} applications...[/bold green]"))
            
            for cat, i in selected_apps:
                install_curated_app(CURATED_APPS[cat][i])

            console.print("\n[bold green]Batch installation complete![/bold green]")
            Prompt.ask("Press Enter to continue")
            selected_apps.clear()
            
        else:
            # Parse selection
            parts = choice.split(',')
            for part in parts:
                part = part.strip()
                if '-' in part:
                    try:
                        start, end = map(int, part.split('-'))
                        for idx in range(start, end + 1):
                            real_idx = idx - 1
                            if 0 <= real_idx < len(display_list):
                                target = display_list[real_idx]
                                if target in selected_apps:
                                    selected_apps.remove(target)
                                else:
                                    selected_apps.add(target)
                    except ValueError:
                        pass
                elif part.isdigit():
                    idx = int(part) - 1
                    if 0 <= idx < len(display_list):
                        target = display_list[idx]
                        if target in selected_apps:
                            selected_apps.remove(target)
                        else:
                            selected_apps.add(target)

def interactive_tweaks():
    optimizer = SystemOptimizer(console, guard)
    while True:
        console.clear()
        console.print(Panel("[bold white]Advanced System Optimization[/bold white]", subtitle="Performance Tweaks"))
        
        console.print("1. [cyan]Optimize Swappiness[/cyan] (Better desktop responsiveness)")
        console.print("2. [cyan]Optimize Network (BBR)[/cyan] (Faster internet speeds)")
        console.print("3. [cyan]Optimize Filesystem[/cyan] (TRIM & Inotify)")
        console.print("4. [cyan]Optimize Gaming[/cyan] (max_map_count for Steam)")
        console.print("5. [cyan]Optimize VFS Cache[/cyan] (System responsiveness)")
        console.print("6. [bold red]Revert All Optimizations[/bold red]")
        console.print("7. [bold]Back[/bold]")
        
        choice = Prompt.ask("Choose an option", choices=["1", "2", "3", "4", "5", "6", "7"])
        
        if choice == "1":
            optimizer.optimize_swappiness()
        elif choice == "2":
            optimizer.optimize_network()
        elif choice == "3":
            optimizer.optimize_filesystem()
        elif choice == "4":
            optimizer.optimize_gaming()
        elif choice == "5":
            optimizer.optimize_vfs()
        elif choice == "6":
            if Confirm.ask("[bold red]Are you sure you want to revert all optimizations?[/bold red]"):
                optimizer.revert_optimizations()
        elif choice == "7":
            break
        
        Prompt.ask("Press Enter to continue")

def interactive_deploy():
    console.clear()
    console.print(Panel("[bold green]One-Click System Setup[/bold green]", subtitle="Pick a profile"))

    if not PROFILES:
        console.print("[red]No setup profiles found (profiles.json missing or empty).[/red]")
        Prompt.ask("Press Enter to return to menu")
        return

    names = list(PROFILES.keys())
    for idx, name in enumerate(names, 1):
        p = PROFILES[name]
        console.print(f"{idx}. [bold cyan]{name}[/bold cyan] - {p['desc']}")

    choice = Prompt.ask("Choose a profile (or 'b' to back)", default="b")
    if choice.lower() == 'b':
        return
    if not choice.isdigit() or not (1 <= int(choice) <= len(names)):
        console.print("[red]Invalid selection.[/red]")
        Prompt.ask("Press Enter to continue")
        return

    profile_name = names[int(choice) - 1]
    profile = PROFILES[profile_name]

    console.print(f"\n[bold]{profile_name}[/bold] will:")
    console.print("  - Update system packages")
    if profile.get("tweaks"):
        console.print(f"  - Apply tweaks: {', '.join(profile['tweaks'])}")
    if profile.get("security"):
        console.print(f"  - Enable security hardening: {', '.join(profile['security'])}")
    if profile.get("apps"):
        console.print(f"  - Install {len(profile['apps'])} curated apps")
    if profile.get("gaming_stack"):
        console.print("  - Install gaming performance tools (gamemode, mangohud)")
    if profile.get("check_nvidia"):
        console.print("  - Check for an NVIDIA GPU and offer to install drivers")

    if not Confirm.ask("\n[bold yellow]Ready to start?[/bold yellow]"):
        return

    optimizer = SystemOptimizer(console, guard)
    security_mgr = SecurityManager(console, guard)
    driver_mgr = DriverManager(console, guard)
    system_mgr = managers[2] if len(managers) > 2 else None

    console.print("\n[bold blue]Updating system packages...[/bold blue]")
    optimizer.update_system()

    for method_name in profile.get("tweaks", []):
        method = getattr(optimizer, method_name, None)
        if method:
            method()

    for action in profile.get("security", []):
        if action == "firewall":
            security_mgr.enable_firewall()
        elif action == "fail2ban":
            security_mgr.install_fail2ban(system_mgr)

    if profile.get("apps"):
        console.print("\n[bold blue]Installing apps...[/bold blue]")
        for cat, app_name in profile["apps"]:
            app_data = next((a for a in CURATED_APPS.get(cat, []) if a["name"] == app_name), None)
            if app_data:
                install_curated_app(app_data)
            else:
                console.print(f"[yellow]Could not find data for {app_name}[/yellow]")

    if profile.get("gaming_stack"):
        console.print("\n[bold blue]Installing gaming performance tools...[/bold blue]")
        driver_mgr.install_gaming_stack(system_mgr)

    if profile.get("check_nvidia") and driver_mgr.detect_nvidia():
        console.print("\n[yellow]An NVIDIA GPU was detected.[/yellow]")
        if Confirm.ask("Install the proprietary NVIDIA driver?"):
            driver_mgr.install_nvidia_driver(system_mgr)

    console.print(f"\n[bold green]✨ {profile_name} setup complete! ✨[/bold green]")
    Prompt.ask("Press Enter to return to menu")

def interactive_history():
    while True:
        console.clear()
        console.print(guard.history())
        console.print("\n[bold]Controls:[/bold]")
        console.print("  [cyan]u[/cyan] : Undo last action")
        console.print("  [cyan]a[/cyan] : Undo ALL reversible actions")
        console.print("  [red]b[/red] : Back")

        choice = Prompt.ask("Selection", default="b")
        if choice.lower() == 'b':
            break
        elif choice.lower() == 'u':
            guard.undo(1)
            Prompt.ask("Press Enter to continue")
        elif choice.lower() == 'a':
            if Confirm.ask("[bold red]Undo every reversible action ULPM has taken?[/bold red]"):
                guard.undo(None)
                Prompt.ask("Press Enter to continue")

def interactive_security():
    security_mgr = SecurityManager(console, guard)
    driver_mgr = DriverManager(console, guard)
    shell_setup = ShellSetup(console, guard)
    system_mgr = managers[2] if len(managers) > 2 else None

    while True:
        console.clear()
        console.print(Panel("[bold white]Security, Drivers & Shell[/bold white]"))

        backend = security_mgr.firewall_backend()
        fw_label = f"{backend} - {security_mgr.firewall_status()}" if backend else "not available"
        console.print(f"1. [cyan]Enable Firewall[/cyan] (current: {fw_label})")
        console.print("2. [cyan]Install & Enable fail2ban[/cyan]")
        console.print("3. [bold red]Harden SSH[/bold red] (disables password login - key auth only)")
        console.print("4. [cyan]Detect & Install NVIDIA Driver[/cyan]")
        console.print("5. [cyan]Install Gaming Performance Tools[/cyan] (gamemode, mangohud)")
        console.print("6. [cyan]Install zsh + starship[/cyan]")
        console.print("7. [cyan]Install fish[/cyan]")
        console.print("8. [bold]Back[/bold]")

        choice = Prompt.ask("Choose an option", choices=["1", "2", "3", "4", "5", "6", "7", "8"])

        if choice == "1":
            security_mgr.enable_firewall()
        elif choice == "2":
            security_mgr.install_fail2ban(system_mgr)
        elif choice == "3":
            console.print("[bold red]Warning:[/bold red] this disables SSH password login and root login.")
            console.print("Only continue if you already have SSH key-based login working -- on a remote")
            console.print("machine, getting this wrong can lock you out entirely.")
            if Confirm.ask("Do you have working SSH key-based login set up already?", default=False):
                if Confirm.ask("[bold red]Confirm: harden SSH now?[/bold red]"):
                    security_mgr.harden_ssh()
            else:
                console.print("[yellow]Skipped. Set up SSH keys first.[/yellow]")
        elif choice == "4":
            if driver_mgr.detect_nvidia():
                console.print("[green]NVIDIA GPU detected.[/green]")
                if Confirm.ask("Install the proprietary NVIDIA driver?"):
                    driver_mgr.install_nvidia_driver(system_mgr)
            else:
                console.print("[yellow]No NVIDIA GPU detected.[/yellow]")
        elif choice == "5":
            driver_mgr.install_gaming_stack(system_mgr)
        elif choice == "6":
            shell_setup.install_shell(system_mgr, "zsh")
        elif choice == "7":
            shell_setup.install_shell(system_mgr, "fish")
        elif choice == "8":
            break

        Prompt.ask("Press Enter to continue")

def main_menu():
    while True:
        console.clear()
        console.print(Panel("[bold magenta]Universal Linux Package Manager (ULPM)[/bold magenta]", subtitle="Flatpak, Snap & System Packages"))
        console.print("1. [bold cyan]Search & Install[/bold cyan]")
        console.print("2. [bold green]Curated Apps[/bold green]")
        console.print("3. [bold yellow]List & Manage Installed[/bold yellow]")
        console.print("4. [bold blue]Update All[/bold blue]")
        console.print("5. [bold white]Advanced Optimization[/bold white]")
        console.print("6. [bold green]One-Click Setup[/bold green]")
        console.print("7. [bold cyan]Change History / Undo[/bold cyan]")
        console.print("8. [bold white]Security, Drivers & Shell[/bold white]")
        console.print("9. [bold red]Exit[/bold red]")

        choice = Prompt.ask("Choose an option", choices=["1", "2", "3", "4", "5", "6", "7", "8", "9"], default="1")

        if choice == "1":
            interactive_search()
        elif choice == "2":
            interactive_curated()
        elif choice == "3":
            interactive_list()
        elif choice == "4":
            update()
            Prompt.ask("Press Enter to continue")
        elif choice == "5":
            interactive_tweaks()
        elif choice == "6":
            interactive_deploy()
        elif choice == "7":
            interactive_history()
        elif choice == "8":
            interactive_security()
        elif choice == "9":
            console.print("[bold]Goodbye![/bold]")
            break

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview system-modifying actions without applying them."),
):
    """
    Universal Linux Package Manager (ULPM)
    A beautiful CLI for managing Flatpak, Snap, and System Packages.
    If no command is given, launches interactive mode.
    """
    guard.dry_run = dry_run
    if ctx.invoked_subcommand is None:
        bootstrap_app_stores()
        main_menu()

@app.command()
def search(query: str):
    """Search for applications (Flatpak, Snap, & DNF)."""
    all_results = []
    with console.status(f"[bold green]Searching for '{query}'...[/bold green]", spinner="dots"):
        for mgr in managers:
            results = mgr.search(query)
            for r in results:
                r['manager'] = mgr
            all_results.extend(results)

    if not all_results:
        console.print(f"[yellow]No results found for '{query}'.[/yellow]")
        return

    table = Table(title=f"Search Results for '{query}'", show_header=True, header_style="bold magenta")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Type", style="bold")
    table.add_column("Description")
    table.add_column("App ID", style="dim")
    table.add_column("Version", style="green")

    for r in all_results:
        mgr_style = r['manager'].color
        table.add_row(
            r['name'], 
            f"[{mgr_style}]{r['manager'].name}[/{mgr_style}]", 
            r['description'], 
            r['id'], 
            r['version']
        )

    console.print(table)

@app.command()
def install(app_id: str, manager: str = typer.Option("flatpak", help="Manager to use: flatpak, snap, dnf, apt, pacman, zypper, apk, xbps, or portage")):
    """Install an application."""
    mgr = next((m for m in managers if m.name.lower() == manager.lower()), None)
    if not mgr:
        console.print(f"[red]Unknown manager: {manager}[/red]")
        return

    console.print(Panel(f"Installing [bold cyan]{app_id}[/bold cyan] via {mgr.name}...", border_style=mgr.color))
    mgr.install(app_id)

@app.command()
def update():
    """Update all installed applications (Flatpak, Snap, & DNF)."""
    for mgr in managers:
        console.print(Panel(f"Updating {mgr.name} apps...", border_style=mgr.color))
        mgr.update()
    console.print("\n[bold green]All updates complete![/bold green]")

@app.command("list")
def list_apps():
    """List installed applications."""
    all_apps = []
    with console.status("[bold green]Fetching installed apps...[/bold green]"):
        for mgr in managers:
            apps = mgr.list_installed()
            for a in apps:
                a['manager'] = mgr
            all_apps.extend(apps)

    if not all_apps:
        console.print("[yellow]No apps installed.[/yellow]")
        return

    table = Table(title="Installed Applications", show_header=True, header_style="bold magenta")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Type", style="bold")
    table.add_column("App ID", style="dim")
    table.add_column("Version", style="green")

    for r in all_apps:
        mgr_style = r['manager'].color
        table.add_row(
            r['name'], 
            f"[{mgr_style}]{r['manager'].name}[/{mgr_style}]", 
            r['id'], 
            r['version']
        )

    console.print(table)

@app.command()
def remove(app_id: str, manager: str = typer.Option("flatpak", help="Manager to use: flatpak, snap, dnf, apt, pacman, zypper, apk, xbps, or portage")):
    """Uninstall an application."""
    mgr = next((m for m in managers if m.name.lower() == manager.lower()), None)
    if not mgr:
        console.print(f"[red]Unknown manager: {manager}[/red]")
        return

    if typer.confirm(f"Are you sure you want to remove {app_id} from {mgr.name}?", default=True):
        mgr.remove(app_id)
    else:
        console.print("[yellow]Operation cancelled.[/yellow]")

@app.command()
def info(app_id: str, manager: str = typer.Option("flatpak", help="Manager to use: flatpak, snap, dnf, apt, pacman, zypper, apk, xbps, or portage")):
    """Show details about an application."""
    mgr = next((m for m in managers if m.name.lower() == manager.lower()), None)
    if not mgr:
        console.print(f"[red]Unknown manager: {manager}[/red]")
        return
    
    info_text = mgr.info(app_id)
    if info_text:
        console.print(Panel(info_text, title=f"Info: {app_id}", border_style=mgr.color))
    else:
        console.print(f"[red]No info found for {app_id}[/red]")

@app.command()
def undo(
    all: bool = typer.Option(False, "--all", help="Undo every reversible action instead of just the last one."),
    count: int = typer.Option(1, "--count", help="Number of recent reversible actions to undo."),
):
    """Reverse recent system-modifying actions (installs, tweaks) tracked in the change log."""
    guard.undo(None if all else count)

@app.command()
def history():
    """Show the recent history of system-modifying actions ULPM has taken."""
    console.print(guard.history())

def cli():
    app()

if __name__ == "__main__":
    cli()
