import shutil
from rich.console import Console
from .safety import SystemGuard

class SystemOptimizer:
    def __init__(self, console: Console, guard: SystemGuard):
        self.console = console
        self.guard = guard

    def update_system(self):
        """Updates the system packages."""
        if shutil.which("apt"):
            self.guard.run(["sudo", "apt", "update"], "Updating System (APT) - refreshing package index")
            return self.guard.run(["sudo", "apt", "upgrade", "-y"], "Updating System (APT) - upgrading packages")
        elif shutil.which("dnf"):
            return self.guard.run(["sudo", "dnf", "update", "-y"], "Updating System (DNF)")
        elif shutil.which("pacman"):
            return self.guard.run(["sudo", "pacman", "-Syu", "--noconfirm"], "Updating System (Pacman)")
        elif shutil.which("zypper"):
            return self.guard.run(["sudo", "zypper", "--non-interactive", "update"], "Updating System (Zypper)")
        elif shutil.which("apk"):
            self.guard.run(["sudo", "apk", "update"], "Updating System (APK) - refreshing package index")
            return self.guard.run(["sudo", "apk", "upgrade"], "Updating System (APK) - upgrading packages")
        else:
            self.console.print("[yellow]No supported package manager found for update.[/yellow]")
            return False

    def cleanup_system(self):
        """Removes unused packages and caches."""
        success = True
        if shutil.which("apt"):
            success &= self.guard.run(["sudo", "apt", "autoremove", "-y"], "Removing unused APT packages")
            success &= self.guard.run(["sudo", "apt", "clean"], "Cleaning APT cache")
        elif shutil.which("dnf"):
            success &= self.guard.run(["sudo", "dnf", "autoremove", "-y"], "Removing unused DNF packages")
            success &= self.guard.run(["sudo", "dnf", "clean", "all"], "Cleaning DNF cache")
        elif shutil.which("pacman"):
            success &= self.guard.run(["sudo", "pacman", "-Sc", "--noconfirm"], "Cleaning Pacman cache")

        if shutil.which("flatpak"):
            success &= self.guard.run(["flatpak", "uninstall", "--unused", "-y"], "Removing unused Flatpak runtimes")

        if shutil.which("journalctl"):
            success &= self.guard.run(["sudo", "journalctl", "--vacuum-time=2weeks"], "Vacuuming system logs (older than 2 weeks)")

        return success

    def optimize_swappiness(self):
        """Sets swappiness to 10 for better desktop performance."""
        target_value = 10
        try:
            with open("/proc/sys/vm/swappiness", "r") as f:
                current = int(f.read().strip())

            if current <= target_value:
                self.console.print(f"[green]✓ Swappiness is already optimized (Value: {current}).[/green]")
                return True

            self.console.print(f"[blue]Current swappiness: {current}. Optimizing to {target_value}...[/blue]")

            if not self.guard.run(
                ["sudo", "sysctl", f"vm.swappiness={target_value}"], "Applying swappiness tweak",
                reversible=True, reverse_cmd=["sudo", "sysctl", f"vm.swappiness={current}"], tag="tweak"
            ):
                return False

            return self.guard.write_file(
                "/etc/sysctl.d/99-swappiness.conf", f"vm.swappiness={target_value}\n",
                "Making swappiness tweak persistent", use_sudo=True, tag="tweak"
            )

        except FileNotFoundError:
            self.console.print("[yellow]Could not read /proc/sys/vm/swappiness. Skipping.[/yellow]")
            return False
        except Exception as e:
            self.console.print(f"[red]Error checking swappiness: {e}[/red]")
            return False

    def optimize_network(self):
        """Enables BBR congestion control for better network speeds."""
        try:
            with open("/proc/sys/net/ipv4/tcp_congestion_control", "r") as f:
                if "bbr" in f.read():
                    self.console.print("[green]✓ Network (BBR) is already enabled.[/green]")
                    return True

            self.console.print("[blue]Enabling BBR Congestion Control...[/blue]")

            config = "net.core.default_qdisc=fq\nnet.ipv4.tcp_congestion_control=bbr\n"
            if self.guard.write_file(
                "/etc/sysctl.d/99-ulpm-network.conf", config, "Creating BBR config",
                use_sudo=True, tag="tweak"
            ):
                return self.guard.run(["sudo", "sysctl", "--system"], "Applying network tweaks", tag="tweak")
            return False
        except Exception as e:
            self.console.print(f"[red]Error enabling BBR: {e}[/red]")
            return False

    def optimize_filesystem(self):
        """Optimizes filesystem performance (TRIM & Inotify)."""
        success = True

        success &= self.guard.run(["sudo", "fstrim", "-av"], "Trimming SSDs", tag="tweak")

        success &= self.guard.write_file(
            "/etc/sysctl.d/99-ulpm-inotify.conf", "fs.inotify.max_user_watches=524288\n",
            "Configuring inotify limits", use_sudo=True, tag="tweak"
        )
        success &= self.guard.run(
            ["sudo", "sysctl", "-p", "/etc/sysctl.d/99-ulpm-inotify.conf"],
            "Applying inotify limits", tag="tweak"
        )

        return success

    def optimize_gaming(self):
        """Optimizes system for gaming (max_map_count)."""
        if self.guard.write_file(
            "/etc/sysctl.d/99-ulpm-gaming.conf", "vm.max_map_count=2147483642\n",
            "Setting max_map_count for gaming", use_sudo=True, tag="tweak"
        ):
            return self.guard.run(
                ["sudo", "sysctl", "-p", "/etc/sysctl.d/99-ulpm-gaming.conf"],
                "Applying gaming tweaks", tag="tweak"
            )
        return False

    def optimize_vfs(self):
        """Optimizes VFS cache pressure for better responsiveness."""
        if self.guard.write_file(
            "/etc/sysctl.d/99-ulpm-vfs.conf", "vm.vfs_cache_pressure=50\n",
            "Setting VFS cache pressure", use_sudo=True, tag="tweak"
        ):
            return self.guard.run(
                ["sudo", "sysctl", "-p", "/etc/sysctl.d/99-ulpm-vfs.conf"],
                "Applying VFS tweaks", tag="tweak"
            )
        return False

    def revert_optimizations(self):
        """Reverts every tweak applied through this class via the change-tracking ledger."""
        self.console.print("[bold red]Reverting all optimizations...[/bold red]")
        self.guard.undo(n=None, tag="tweak")
        self.console.print("[yellow]Note: A reboot is recommended to fully reset kernel parameters.[/yellow]")
        return True
