import json
import os
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.table import Table

STATE_DIR = Path.home() / ".local" / "state" / "ulpm"
BACKUP_DIR = STATE_DIR / "backups"
LEDGER_FILE = STATE_DIR / "actions.log"


class SystemGuard:
    """Single choke point for every system-modifying action (file writes, shell-outs).
    Gives every caller --dry-run preview, pre-change backups, and a shared undo
    ledger for free, instead of each feature reinventing its own revert logic."""

    def __init__(self, console: Console, dry_run: bool = False):
        self.console = console
        self.dry_run = dry_run

    def _new_id(self) -> str:
        return f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"

    def _append_ledger(self, entry: dict) -> None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(LEDGER_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def _read_ledger(self) -> List[dict]:
        if not LEDGER_FILE.exists():
            return []
        entries = []
        with open(LEDGER_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return entries

    def write_file(self, path: str, content: str, description: str, use_sudo: bool = False,
                   tag: Optional[str] = None) -> bool:
        """Write content to a file, backing up any prior content first so it can be undone."""
        path = str(path)
        existed = os.path.exists(path)

        if self.dry_run:
            verb = "overwrite" if existed else "create"
            self.console.print(f"[cyan][DRY-RUN][/cyan] Would {verb} {path} ({description})")
            return True

        entry_id = self._new_id()
        backup_path = None

        if existed:
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            backup_path = str(BACKUP_DIR / f"{entry_id}_{Path(path).name}")
            try:
                shutil.copy2(path, backup_path)
            except PermissionError:
                try:
                    subprocess.run(["sudo", "cp", "-p", path, backup_path], check=True)
                except Exception as e:
                    self.console.print(f"[red]Failed to back up {path}: {e}[/red]")
                    return False
            except Exception as e:
                self.console.print(f"[red]Failed to back up {path}: {e}[/red]")
                return False

        try:
            if use_sudo:
                subprocess.run(["sudo", "tee", path], input=content, text=True,
                                capture_output=True, check=True)
            else:
                with open(path, "w") as f:
                    f.write(content)
        except Exception as e:
            self.console.print(f"[red]✗ {description} failed: {e}[/red]")
            return False

        self.console.print(f"[green]✓ {description}[/green]")
        self._append_ledger({
            "id": entry_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            "action": "write_file",
            "description": description,
            "path": path,
            "existed": existed,
            "backup_path": backup_path,
            "use_sudo": use_sudo,
            "reversible": True,
            "tag": tag,
        })
        return True

    def remove_file(self, path: str, description: str, use_sudo: bool = False,
                     tag: Optional[str] = None) -> bool:
        """Delete a file, backing it up first so it can be restored via undo."""
        path = str(path)

        if self.dry_run:
            self.console.print(f"[cyan][DRY-RUN][/cyan] Would remove {path} ({description})")
            return True

        if not os.path.exists(path):
            return True

        entry_id = self._new_id()
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        backup_path = str(BACKUP_DIR / f"{entry_id}_{Path(path).name}")
        try:
            shutil.copy2(path, backup_path)
        except Exception:
            backup_path = None  # best-effort; still proceed with removal

        try:
            if use_sudo:
                subprocess.run(["sudo", "rm", path], check=True)
            else:
                os.remove(path)
        except Exception as e:
            self.console.print(f"[red]✗ {description} failed: {e}[/red]")
            return False

        self.console.print(f"[green]✓ {description}[/green]")
        self._append_ledger({
            "id": entry_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            "action": "remove_file",
            "description": description,
            "path": path,
            "backup_path": backup_path,
            "use_sudo": use_sudo,
            "reversible": backup_path is not None,
            "tag": tag,
        })
        return True

    def run(self, cmd: List[str], description: str, reversible: bool = False,
            reverse_cmd: Optional[List[str]] = None, tag: Optional[str] = None) -> bool:
        """Run a command, logging it for history/dry-run/undo. cmd is always a list
        (no shell=True) so nothing here is exposed to shell injection."""
        if self.dry_run:
            self.console.print(f"[cyan][DRY-RUN][/cyan] Would run: {' '.join(cmd)} ({description})")
            return True

        self.console.print(f"[blue]{description}...[/blue]")
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError:
            self.console.print(f"[red]✗ {description} failed.[/red]")
            return False
        except FileNotFoundError:
            self.console.print(f"[red]✗ {description} failed: command not found.[/red]")
            return False

        self.console.print(f"[green]✓ {description} complete.[/green]")
        self._append_ledger({
            "id": self._new_id(),
            "ts": datetime.now(timezone.utc).isoformat(),
            "action": "run",
            "description": description,
            "cmd": cmd,
            "reverse_cmd": reverse_cmd,
            "reversible": bool(reversible and reverse_cmd),
            "tag": tag,
        })
        return True

    def _pending_entries(self, tag: Optional[str] = None) -> List[dict]:
        entries = self._read_ledger()
        reversed_ids = {e["reverses"] for e in entries if e.get("reverses")}
        return [
            e for e in entries
            if e.get("reversible") and e["id"] not in reversed_ids and not e.get("reverses")
            and (tag is None or e.get("tag") == tag)
        ]

    def _reverse_entry(self, entry: dict) -> bool:
        action = entry["action"]
        use_sudo = entry.get("use_sudo", False)

        if action == "write_file":
            path = entry["path"]
            if entry["existed"] and entry.get("backup_path") and os.path.exists(entry["backup_path"]):
                with open(entry["backup_path"], "r") as f:
                    original = f.read()
                if use_sudo:
                    result = subprocess.run(["sudo", "tee", path], input=original, text=True,
                                             capture_output=True)
                    return result.returncode == 0
                with open(path, "w") as f:
                    f.write(original)
                return True
            elif not entry["existed"]:
                if use_sudo:
                    return subprocess.run(["sudo", "rm", "-f", path]).returncode == 0
                Path(path).unlink(missing_ok=True)
                return True
            return False

        elif action == "remove_file":
            if entry.get("backup_path") and os.path.exists(entry["backup_path"]):
                if use_sudo:
                    return subprocess.run(["sudo", "cp", entry["backup_path"], entry["path"]]).returncode == 0
                shutil.copy2(entry["backup_path"], entry["path"])
                return True
            return False

        elif action == "run":
            reverse_cmd = entry.get("reverse_cmd")
            if reverse_cmd:
                try:
                    subprocess.run(reverse_cmd, check=True)
                    return True
                except Exception:
                    return False
            return False

        return False

    def undo(self, n: Optional[int] = 1, tag: Optional[str] = None) -> None:
        """Reverse the last `n` reversible actions, or all of them if n is None.
        Pass `tag` to scope this to a subset (e.g. "tweak") instead of everything."""
        pending = self._pending_entries(tag=tag)
        if not pending:
            self.console.print("[yellow]Nothing to undo.[/yellow]")
            return

        targets = pending if n is None else pending[-n:]
        for entry in reversed(targets):
            desc = entry["description"]
            if self._reverse_entry(entry):
                self.console.print(f"[green]✓ Reverted:[/green] {desc}")
                self._append_ledger({
                    "id": self._new_id(),
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "action": "undo",
                    "description": f"Undo: {desc}",
                    "reverses": entry["id"],
                    "reversible": False,
                })
            else:
                self.console.print(f"[red]✗ Could not revert:[/red] {desc}")

    def history(self, limit: int = 20) -> Table:
        entries = self._read_ledger()
        reversed_ids = {e["reverses"] for e in entries if e.get("reverses")}

        table = Table(title="ULPM Change History", show_header=True, header_style="bold magenta")
        table.add_column("When", style="dim")
        table.add_column("Action")
        table.add_column("Status")

        forward = [e for e in entries if e.get("action") != "undo"]
        for entry in forward[-limit:]:
            if entry.get("reversible"):
                status = "[yellow]reverted[/yellow]" if entry["id"] in reversed_ids else "[green]active[/green]"
            else:
                status = "[dim]not reversible[/dim]"
            table.add_row(entry.get("ts", "")[:19].replace("T", " "), entry.get("description", ""), status)

        return table
