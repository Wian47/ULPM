import typer
import subprocess
import sys
import shutil
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, Confirm
from typing import Optional, List, Dict

app = typer.Typer(help="A beautiful CLI for managing Flatpak, Snap, and DNF apps on Fedora.")
console = Console()

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

    def _run(self, args: List[str], capture: bool = True) -> str:
        cmd = ["flatpak"] + args
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

    def install(self, app_id: str):
        # Interactive
        self._run(["install", app_id], capture=False)

    def remove(self, app_id: str):
        # Interactive
        self._run(["uninstall", app_id], capture=False)

    def update(self):
        self._run(["update"], capture=False)

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

    def install(self, app_id: str):
        # Snaps often need sudo. subprocess.run without capture allows sudo prompt.
        console.print("[yellow]Note: Snap installation may require sudo password.[/yellow]")
        self._run(["install", app_id], capture=False)

    def remove(self, app_id: str):
        console.print("[yellow]Note: Snap removal may require sudo password.[/yellow]")
        self._run(["remove", app_id], capture=False)

    def update(self):
        console.print("[yellow]Note: Snap refresh may require sudo password.[/yellow]")
        self._run(["refresh"], capture=False)

    def info(self, app_id: str) -> str:
        return self._run(["info", app_id])

class DnfManager(PackageManager):
    name = "DNF"
    color = "yellow"

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
        # dnf list installed is HUGE. We probably shouldn't list ALL dnf packages by default in the "list" view 
        # unless requested, or maybe just user-installed ones.
        # `dnf history userinstalled` is better but might not exist on all versions.
        # Let's stick to a limit or just not implement list_installed for DNF to avoid cluttering the UI 
        # with 2000 system libs.
        # Alternatively, return an empty list or only top-level apps.
        # For this "All in one" tool, maybe we skip DNF list for now to keep it usable, 
        # or we try `dnf list installed userinstalled` if supported.
        return [] 

    def install(self, app_id: str):
        console.print("[yellow]Note: DNF installation requires sudo.[/yellow]")
        subprocess.run(["sudo", "dnf", "install", app_id], check=False)

    def remove(self, app_id: str):
        console.print("[yellow]Note: DNF removal requires sudo.[/yellow]")
        subprocess.run(["sudo", "dnf", "remove", app_id], check=False)

    def update(self):
        console.print("[yellow]Note: DNF update requires sudo.[/yellow]")
        subprocess.run(["sudo", "dnf", "update"], check=False)

    def info(self, app_id: str) -> str:
        return self._run(["info", app_id])

# Initialize Managers
managers = [FlatpakManager(), SnapManager(), DnfManager()]

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

def main_menu():
    while True:
        console.clear()
        console.print(Panel("[bold magenta]Universal Linux Package Manager[/bold magenta]", subtitle="Flatpak, Snap & DNF"))
        console.print("1. [bold cyan]Search & Install[/bold cyan]")
        console.print("2. [bold green]List & Manage Installed[/bold green]")
        console.print("3. [bold blue]Update All[/bold blue]")
        console.print("4. [bold red]Exit[/bold red]")
        
        choice = Prompt.ask("Choose an option", choices=["1", "2", "3", "4"], default="1")
        
        if choice == "1":
            interactive_search()
        elif choice == "2":
            interactive_list()
        elif choice == "3":
            update()
            Prompt.ask("Press Enter to continue")
        elif choice == "4":
            console.print("[bold]Goodbye![/bold]")
            break

@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """
    A beautiful CLI for managing Flatpak, Snap, and DNF apps.
    If no command is given, launches interactive mode.
    """
    if ctx.invoked_subcommand is None:
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
def install(app_id: str, manager: str = typer.Option("flatpak", help="Manager to use: flatpak, snap, or dnf")):
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
def remove(app_id: str, manager: str = typer.Option("flatpak", help="Manager to use: flatpak, snap, or dnf")):
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
def info(app_id: str, manager: str = typer.Option("flatpak", help="Manager to use: flatpak, snap, or dnf")):
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

if __name__ == "__main__":
    app()
