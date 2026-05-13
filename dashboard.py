from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Static, RichLog, Label
from textual.containers import Horizontal, Vertical
from textual.binding import Binding
import json
import subprocess
import asyncio
from pathlib import Path

REGISTRY_FILE = Path("/root/projects/mcswarm/agents/fleet-registry.json")

def load_registry():
    if REGISTRY_FILE.exists():
        with open(REGISTRY_FILE, "r") as f:
            return json.load(f)
    return {"agents": {}, "used_names": []}

class DashboardApp(App):
    CSS = """
    #left-pane {
        width: 60%;
        height: 100%;
        border-right: solid green;
    }
    #right-pane {
        width: 40%;
        height: 100%;
    }
    #details-pane {
        height: 40%;
        border-bottom: solid green;
        padding: 1;
    }
    #log-pane {
        height: 60%;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("s", "start_agent", "Start"),
        Binding("x", "stop_agent", "Stop"),
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
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#agents_table", DataTable)
        table.add_columns("Name", "Role", "Purpose", "Status")
        table.cursor_type = "row"
        self.refresh_table()
        self.log_task = None
        self.current_slug = None

    def refresh_table(self):
        table = self.query_one("#agents_table", DataTable)
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
            
            table.add_row(name, role, info["purpose"], status, key=name)

    def action_refresh(self) -> None:
        self.refresh_table()

    def action_start_agent(self) -> None:
        if self.current_slug:
            subprocess.run(["systemctl", "--user", "start", self.current_slug])
            self.refresh_table()

    def action_stop_agent(self) -> None:
        if self.current_slug:
            subprocess.run(["systemctl", "--user", "stop", self.current_slug])
            self.refresh_table()

    async def tail_logs(self, slug: str):
        log_view = self.query_one("#logs_view", RichLog)
        log_view.clear()
        
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
                log_view.write(line.decode().strip())
        except asyncio.CancelledError:
            proc.terminate()

    async def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        name = event.row_key.value
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

To test MCP tools manually:
`podman exec -it systemd-{info['profile']} hermes mcp inspect`
"""
        self.query_one("#details_content", Static).update(details)

        if self.log_task:
            self.log_task.cancel()
        self.log_task = asyncio.create_task(self.tail_logs(self.current_slug))

if __name__ == "__main__":
    app = DashboardApp()
    app.run()
