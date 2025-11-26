import subprocess
import shutil
import os
from rich.console import Console

class SystemOptimizer:
    def __init__(self, console: Console):
        self.console = console

    def _run(self, cmd: str, description: str) -> bool:
        self.console.print(f"[blue]{description}...[/blue]")
        try:
            subprocess.run(cmd, shell=True, check=True)
            self.console.print(f"[green]✓ {description} complete.[/green]")
            return True
        except subprocess.CalledProcessError:
            self.console.print(f"[red]✗ {description} failed.[/red]")
            return False

    def update_system(self):
        """Updates the system packages."""
        if shutil.which("apt"):
            return self._run("sudo apt update && sudo apt upgrade -y", "Updating System (APT)")
        elif shutil.which("dnf"):
            return self._run("sudo dnf update -y", "Updating System (DNF)")
        elif shutil.which("pacman"):
            return self._run("sudo pacman -Syu --noconfirm", "Updating System (Pacman)")
        else:
            self.console.print("[yellow]No supported package manager found for update.[/yellow]")
            return False

    def cleanup_system(self):
        """Removes unused packages and caches."""
        success = True
        if shutil.which("apt"):
            success &= self._run("sudo apt autoremove -y && sudo apt clean", "Cleaning APT cache & unused packages")
        elif shutil.which("dnf"):
            success &= self._run("sudo dnf autoremove -y && sudo dnf clean all", "Cleaning DNF cache")
        elif shutil.which("pacman"):
             success &= self._run("sudo pacman -Sc --noconfirm", "Cleaning Pacman cache")
        
        if shutil.which("flatpak"):
            success &= self._run("flatpak uninstall --unused -y", "Removing unused Flatpak runtimes")
            
        # Vacuum journal
        if shutil.which("journalctl"):
            success &= self._run("sudo journalctl --vacuum-time=2weeks", "Vacuuming system logs (older than 2 weeks)")
        
        return success

    def optimize_swappiness(self):
        """Sets swappiness to 10 for better desktop performance."""
        target_value = 10
        try:
            # Check current value
            with open("/proc/sys/vm/swappiness", "r") as f:
                current = int(f.read().strip())
            
            if current <= target_value:
                self.console.print(f"[green]✓ Swappiness is already optimized (Value: {current}).[/green]")
                return True
                
            self.console.print(f"[blue]Current swappiness: {current}. Optimizing to {target_value}...[/blue]")
            
            # Apply immediately
            if not self._run(f"sudo sysctl vm.swappiness={target_value}", "Applying swappiness tweak"):
                return False
            
            # Make persistent
            config_file = "/etc/sysctl.d/99-swappiness.conf"
            cmd = f"echo 'vm.swappiness={target_value}' | sudo tee {config_file}"
            return self._run(cmd, "Making swappiness tweak persistent")
            
        except FileNotFoundError:
             self.console.print("[yellow]Could not read /proc/sys/vm/swappiness. Skipping.[/yellow]")
             return False
        except Exception as e:
            self.console.print(f"[red]Error checking swappiness: {e}[/red]")
            return False
    def optimize_network(self):
        """Enables BBR congestion control for better network speeds."""
        try:
            # Check if already enabled
            with open("/proc/sys/net/ipv4/tcp_congestion_control", "r") as f:
                if "bbr" in f.read():
                    self.console.print("[green]✓ Network (BBR) is already enabled.[/green]")
                    return True

            self.console.print("[blue]Enabling BBR Congestion Control...[/blue]")
            
            # Create config file
            config = "net.core.default_qdisc=fq\nnet.ipv4.tcp_congestion_control=bbr\n"
            cmd = f"echo '{config}' | sudo tee /etc/sysctl.d/99-ulpm-network.conf"
            if self._run(cmd, "Creating BBR config"):
                return self._run("sudo sysctl --system", "Applying network tweaks")
            return False
        except Exception as e:
            self.console.print(f"[red]Error enabling BBR: {e}[/red]")
            return False

    def optimize_filesystem(self):
        """Optimizes filesystem performance (TRIM & Inotify)."""
        success = True
        
        # 1. TRIM
        self.console.print("[blue]Running fstrim...[/blue]")
        success &= self._run("sudo fstrim -av", "Trimming SSDs")
        
        # 2. Inotify
        self.console.print("[blue]Increasing file watchers...[/blue]")
        cmd = "echo 'fs.inotify.max_user_watches=524288' | sudo tee /etc/sysctl.d/99-ulpm-inotify.conf"
        success &= self._run(cmd, "Configuring inotify limits")
        success &= self._run("sudo sysctl -p /etc/sysctl.d/99-ulpm-inotify.conf", "Applying inotify limits")
        
        return success

    def optimize_gaming(self):
        """Optimizes system for gaming (max_map_count)."""
        self.console.print("[blue]Optimizing for Gaming...[/blue]")
        
        # vm.max_map_count for Steam/ESync
        cmd = "echo 'vm.max_map_count=2147483642' | sudo tee /etc/sysctl.d/99-ulpm-gaming.conf"
        if self._run(cmd, "Setting max_map_count"):
            return self._run("sudo sysctl -p /etc/sysctl.d/99-ulpm-gaming.conf", "Applying gaming tweaks")
        return False

    def optimize_vfs(self):
        """Optimizes VFS cache pressure for better responsiveness."""
        self.console.print("[blue]Optimizing VFS Cache Pressure...[/blue]")
        
        # vm.vfs_cache_pressure = 50 (default is usually 100)
        cmd = "echo 'vm.vfs_cache_pressure=50' | sudo tee /etc/sysctl.d/99-ulpm-vfs.conf"
        if self._run(cmd, "Setting VFS cache pressure"):
            return self._run("sudo sysctl -p /etc/sysctl.d/99-ulpm-vfs.conf", "Applying VFS tweaks")
        return False

    def revert_optimizations(self):
        """Reverts all ULPM optimizations."""
        self.console.print("[bold red]Reverting all optimizations...[/bold red]")
        
        files = [
            "/etc/sysctl.d/99-swappiness.conf",
            "/etc/sysctl.d/99-ulpm-network.conf",
            "/etc/sysctl.d/99-ulpm-inotify.conf",
            "/etc/sysctl.d/99-ulpm-gaming.conf",
            "/etc/sysctl.d/99-ulpm-vfs.conf"
        ]
        
        for f in files:
            if os.path.exists(f):
                self._run(f"sudo rm {f}", f"Removing {os.path.basename(f)}")
        
        self.console.print("[yellow]Note: A reboot is recommended to fully reset kernel parameters.[/yellow]")
        return True
