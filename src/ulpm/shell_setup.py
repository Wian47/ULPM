import os
import shutil

from rich.console import Console

from .safety import SystemGuard


class ShellSetup:
    def __init__(self, console: Console, guard: SystemGuard):
        self.console = console
        self.guard = guard

    def install_shell(self, system_mgr, shell_name: str) -> bool:
        """shell_name is 'zsh' or 'fish'. Installs the shell, optionally the
        starship prompt for zsh, and sets it as the user's default via chsh."""
        if not system_mgr:
            self.console.print("[yellow]No system package manager detected; can't install a shell.[/yellow]")
            return False

        if not shutil.which(shell_name):
            if not system_mgr.install(shell_name):
                return False

        if shell_name == "zsh":
            self._install_starship()

        return self._set_default_shell(shell_name)

    def _install_starship(self) -> bool:
        if shutil.which("starship"):
            self.console.print("[green]✓ starship is already installed.[/green]")
            return True
        self.console.print("[blue]Installing the starship prompt...[/blue]")
        return self.guard.run(
            ["sh", "-c", "curl -sS https://starship.rs/install.sh | sh -s -- -y"],
            "Installing starship prompt", tag="shell"
        )

    def _set_default_shell(self, shell_name: str) -> bool:
        shell_path = shutil.which(shell_name)
        if not shell_path:
            self.console.print(f"[red]Couldn't find {shell_name} on PATH after install.[/red]")
            return False

        user = os.environ.get("USER") or os.environ.get("LOGNAME")
        if not user:
            self.console.print("[yellow]Couldn't determine current user; set your default shell manually with chsh.[/yellow]")
            return False

        return self.guard.run(["chsh", "-s", shell_path, user], f"Setting default shell to {shell_name}", tag="shell")
