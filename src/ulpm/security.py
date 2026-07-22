import shutil
import subprocess
from typing import Optional

from rich.console import Console

from .safety import SystemGuard


class SecurityManager:
    """Firewall, fail2ban, and SSH hardening. Everything here is opt-in and
    routed through SystemGuard (tag="security") so it's dry-run-previewable
    and reversible via `ulpm undo`."""

    def __init__(self, console: Console, guard: SystemGuard):
        self.console = console
        self.guard = guard

    def firewall_backend(self) -> Optional[str]:
        if shutil.which("ufw"):
            return "ufw"
        if shutil.which("firewall-cmd"):
            return "firewalld"
        return None

    def firewall_status(self) -> str:
        backend = self.firewall_backend()
        if backend is None:
            return "not installed"
        if backend == "ufw":
            out = subprocess.run(["sudo", "ufw", "status"], capture_output=True, text=True, check=False).stdout
            return "active" if "Status: active" in out else "inactive"
        else:
            result = subprocess.run(["systemctl", "is-active", "firewalld"], capture_output=True, text=True, check=False)
            return "active" if result.stdout.strip() == "active" else "inactive"

    def enable_firewall(self) -> bool:
        backend = self.firewall_backend()
        if backend == "ufw":
            ok = self.guard.run(
                ["sudo", "ufw", "--force", "enable"], "Enabling UFW firewall",
                reversible=True, reverse_cmd=["sudo", "ufw", "disable"], tag="security"
            )
            if ok:
                self.guard.run(["sudo", "ufw", "default", "deny", "incoming"], "Setting UFW default: deny incoming", tag="security")
                self.guard.run(["sudo", "ufw", "default", "allow", "outgoing"], "Setting UFW default: allow outgoing", tag="security")
            return ok
        elif backend == "firewalld":
            return self.guard.run(
                ["sudo", "systemctl", "enable", "--now", "firewalld"], "Enabling firewalld",
                reversible=True, reverse_cmd=["sudo", "systemctl", "disable", "--now", "firewalld"], tag="security"
            )
        else:
            self.console.print("[yellow]No supported firewall (ufw/firewalld) found. Install one via your package manager first.[/yellow]")
            return False

    def install_fail2ban(self, system_mgr) -> bool:
        if shutil.which("fail2ban-client"):
            self.console.print("[green]✓ fail2ban is already installed.[/green]")
            return True
        if not system_mgr:
            self.console.print("[yellow]No system package manager detected; can't install fail2ban.[/yellow]")
            return False
        if not system_mgr.install("fail2ban"):
            return False
        return self.guard.run(
            ["sudo", "systemctl", "enable", "--now", "fail2ban"], "Enabling fail2ban service",
            reversible=True, reverse_cmd=["sudo", "systemctl", "disable", "--now", "fail2ban"], tag="security"
        )

    def harden_ssh(self) -> bool:
        """Disables SSH password auth and root login. The caller is responsible
        for confirming with the user that key-based auth is already set up --
        this can lock you out of a remote machine if it isn't."""
        if not shutil.which("ssh") and not shutil.which("sshd"):
            self.console.print("[yellow]OpenSSH doesn't appear to be installed; skipping.[/yellow]")
            return False

        config_path = "/etc/ssh/sshd_config.d/99-ulpm-hardening.conf"
        content = "PermitRootLogin no\nPasswordAuthentication no\n"
        if not self.guard.write_file(config_path, content, "Writing SSH hardening config", use_sudo=True, tag="security"):
            return False

        # Service is named "sshd" on Fedora/Arch/openSUSE, "ssh" on Debian/Ubuntu.
        for service in ("sshd", "ssh"):
            if self.guard.run(["sudo", "systemctl", "reload", service], f"Reloading {service}", tag="security"):
                return True
        self.console.print("[yellow]Config written but couldn't reload the SSH service automatically; reload it manually.[/yellow]")
        return False
