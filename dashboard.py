from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Static, RichLog, Label, Input
from textual.containers import Horizontal, Vertical
from textual.binding import Binding
import json
import subprocess
import asyncio
from pathlib import Path
from collections import deque
import random

REGISTRY_FILE = Path("/root/projects/mcswarm/agents/fleet-registry.json")

def load_registry():
    if REGISTRY_FILE.exists():
        with open(REGISTRY_FILE, "r") as f:
            return json.load(f)
    return {"agents": {}, "used_names": []}

class DashboardApp(App):
    CSS = """
    #left-pane { width: 60%; height: 100%; border-right: solid green; }
    #right-pane { width: 40%; height: 100%; }
    #details-pane { height: 35%; border-bottom: solid green; padding: 1; }
    #log-pane { height: 65%; }
    #prompt-input { dock: bottom; display: none; margin: 1; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("s", "start_agent", "Start"),
        Binding("x", "stop_agent", "Stop"),
        Binding("space", "toggle_select", "Select"),
        Binding("a", "select_all", "Select All"),
        Binding("p", "prompt", "Prompt"),
        Binding("c", "cancel_prompt", "Cancel Prompt"),
        Binding("escape", "hide_prompt", "Hide Prompt", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Header("Hermes Fleet Dashboard")
        with Horizontal():
            with Vertical(id="left-pane"):
                yield DataTable(id="agents_table")
            with Vertical(id="right-pane"):
                with Vertical(id="details-pane"):
                    yield Label("Agent Details", id="details_label")
                    yield Static("", id="details_content")
                with Vertical(id="log-pane"):
                    yield Label("Logs")
                    yield RichLog(id="logs_view", wrap=True, highlight=True, markup=True)
        yield Input(placeholder="Enter prompt to send to selected agents (Enter to submit, Esc to cancel)...", id="prompt-input")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#agents_table", DataTable)
        table.add_columns("[ ]", "Name", "Role", "Purpose", "Status")
        table.cursor_type = "row"
        self.selected_agents = set()
        self.agent_buffers = {}
        self.journal_tasks = {}
        self.prompt_tasks = {}
        self.refresh_table()
        self.current_name = None
        self.current_slug = None

    def refresh_table(self):
        table = self.query_one("#agents_table", DataTable)
        current_cursor = table.cursor_row
        table.clear()
        self.registry = load_registry()
        for name, info in self.registry["agents"].items():
            slug = info["profile"]
            role = "Coordinator" if info.get("is_coordinator") else "Worker"
            try:
                res = subprocess.run(["systemctl", "--user", "is-active", slug], capture_output=True, text=True)
                status = res.stdout.strip()
            except Exception:
                status = "unknown"
            
            if name in self.selected_agents:
                sel_marker = "✅"
                display_name = f"[bold green]{name}[/bold green]"
            else:
                sel_marker = "⬛"
                display_name = name

            table.add_row(sel_marker, display_name, role, info["purpose"], status, key=name)
            
            if name not in self.agent_buffers:
                self.agent_buffers[name] = deque(maxlen=200)
            if name not in self.journal_tasks:
                self.journal_tasks[name] = asyncio.create_task(self.tail_journal(name, slug))

        if current_cursor is not None and current_cursor < len(table.rows):
            table.move_cursor(row=current_cursor)

    def write_log(self, name: str, text: str):
        if name in self.agent_buffers:
            self.agent_buffers[name].append(text)
        if self.current_name == name:
            self.query_one("#logs_view", RichLog).write(text)

    async def tail_journal(self, name: str, slug: str):
        proc = await asyncio.create_subprocess_exec(
            "journalctl", "--user", "-u", slug, "-f", "-n", "20",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                self.write_log(name, line.decode().strip())
        except asyncio.CancelledError:
            proc.terminate()

    def action_refresh(self) -> None:
        self.refresh_table()

    def action_toggle_select(self) -> None:
        if self.current_name:
            if self.current_name in self.selected_agents:
                self.selected_agents.remove(self.current_name)
            else:
                self.selected_agents.add(self.current_name)
            self.refresh_table()

    def action_select_all(self) -> None:
        names = list(self.registry["agents"].keys())
        if len(self.selected_agents) == len(names):
            self.selected_agents.clear()
        else:
            self.selected_agents.update(names)
        self.refresh_table()

    def action_prompt(self) -> None:
        inp = self.query_one("#prompt-input", Input)
        inp.display = True
        inp.focus()

    def action_hide_prompt(self) -> None:
        inp = self.query_one("#prompt-input", Input)
        inp.display = False
        inp.value = ""
        self.query_one("#agents_table").focus()

    def action_cancel_prompt(self) -> None:
        if self.current_name and self.current_name in self.prompt_tasks:
            self.prompt_tasks[self.current_name].cancel()
            self.write_log(self.current_name, "[bold red]--- PROMPT CANCELLED BY USER ---[/bold red]")
            del self.prompt_tasks[self.current_name]

    def action_start_agent(self) -> None:
        if self.current_slug:
            subprocess.run(["systemctl", "--user", "start", self.current_slug])
            self.refresh_table()

    def action_stop_agent(self) -> None:
        if self.current_slug:
            subprocess.run(["systemctl", "--user", "stop", self.current_slug])
            self.refresh_table()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        prompt_text = event.value.strip()
        self.action_hide_prompt()
        if not prompt_text:
            return

        targets = list(self.selected_agents) if self.selected_agents else ([self.current_name] if self.current_name else [])
        if not targets:
            return

        for name in targets:
            # Jitter to prevent API rate limits
            await asyncio.sleep(random.uniform(0.1, 0.5))
            self.write_log(name, "")
            self.write_log(name, f"[bold cyan]>>> [PROMPT]: {prompt_text}[/bold cyan]")
            
            if name in self.prompt_tasks and not self.prompt_tasks[name].done():
                self.prompt_tasks[name].cancel()
            
            slug = self.registry["agents"][name]["profile"]
            self.prompt_tasks[name] = asyncio.create_task(self.run_prompt(name, slug, prompt_text))

    async def run_prompt(self, name: str, slug: str, prompt: str):
        try:
            proc = await asyncio.create_subprocess_exec(
                "podman", "exec", "-i", f"systemd-{slug}", "hermes", "-z", prompt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                self.write_log(name, line.decode().strip())
            await proc.wait()
            self.write_log(name, f"[bold green]--- PROMPT COMPLETE (Exit {proc.returncode}) ---[/bold green]")
            self.write_log(name, "")
        except asyncio.CancelledError:
            proc.terminate()
            raise
        except Exception as e:
            self.write_log(name, f"[bold red]Error running prompt: {e}[/bold red]")

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        name = event.row_key.value
        self.current_name = name
        info = self.registry["agents"][name]
        self.current_slug = info["profile"]
        
        details = f"""
[b]Name:[/b] {name}
[b]Profile:[/b] {info['profile']}
[b]Model:[/b] {info['model']}
[b]Role:[/b] {"Coordinator" if info.get('is_coordinator') else "Worker"}

[b]How to interact:[/b]
To chat directly with this agent:
`podman exec -it systemd-{info['profile']} hermes chat`
"""
        self.query_one("#details_content", Static).update(details)

        log_view = self.query_one("#logs_view", RichLog)
        log_view.clear()
        if name in self.agent_buffers:
            for line in self.agent_buffers[name]:
                log_view.write(line)

    def cleanup(self):
        for task in self.journal_tasks.values():
            task.cancel()
        for task in self.prompt_tasks.values():
            task.cancel()

    async def on_unmount(self):
        self.cleanup()

if __name__ == "__main__":
    app = DashboardApp()
    app.run()