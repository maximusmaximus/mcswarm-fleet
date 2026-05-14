import os
import sys
import json
import typer
import yaml
import subprocess
import requests
from pathlib import Path
from rich.console import Console
from rich.table import Table
from typing import Optional
from datetime import datetime
import random

app = typer.Typer(help="Fleet Manager for Hermes Agents")
console = Console()

# Configuration Paths
FLEET_DIR = Path("/root/projects/mcswarm")
PROFILES_DIR = FLEET_DIR / "agents"
WORKSPACE_DIR = FLEET_DIR / "workspace"
REGISTRY_FILE = PROFILES_DIR / "fleet-registry.json"
QUADLET_DIR = Path(os.path.expanduser("~/.config/containers/systemd"))

MC_VERBS = [
    "Sprint", "Sashay", "Gallop", "Meander", "Scamper", "Swagger",
    "Ponder", "Mull", "Deliberate", "Ruminate", "Brainstorm", "Muse",
    "Juggle", "Tinker", "Cobble", "Rig", "Whip", "Hammer", "Forge",
    "Blab", "Gossip", "Holler", "Mumble", "Ramble", "Chatter",
    "Fumble", "Bumble", "Stumble", "Tumble", "Fling", "Yeet",
    "Outwit", "Decipher", "Crack", "Unravel", "Sniff", "Sleuth",
    "Chill", "Lurk", "Vibe", "Groove", "Nod", "Shrug",
    "Simmer", "Stew", "Brew", "Marinate", "Ferment",
    "Cajole", "Wheedle", "Finagle", "Hustle", "Scrounge", "Bodge"
]

def ensure_dirs():
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    QUADLET_DIR.mkdir(parents=True, exist_ok=True)

def load_registry():
    if REGISTRY_FILE.exists():
        with open(REGISTRY_FILE, "r") as f:
            return json.load(f)
    return {"agents": {}, "used_names": []}

def save_registry(data):
    with open(REGISTRY_FILE, "w") as f:
        json.dump(data, f, indent=2)

def generate_name(registry):
    used = registry.get("used_names", [])
    available = [f"Mc{v}" for v in MC_VERBS if f"Mc{v}" not in used]
    if not available:
        console.print("[red]Error: All agent names are currently in use.[/red]")
        sys.exit(1)
    return random.choice(available)

def mint_venice_key(name: str, purpose: str):
    admin_key = os.environ.get("VENICE_ADMIN_KEY")
    if not admin_key:
        console.print("[yellow]Warning: VENICE_ADMIN_KEY not set. Generating fake key for development.[/yellow]")
        return "fake_key_dev", "fake_key_id"
    
    headers = {
        "Authorization": f"Bearer {admin_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "apiKeyType": "INFERENCE",
        "description": f"{name} - {purpose}",
        "consumptionLimit": {"usd": 50.0}
    }
    
    try:
        resp = requests.post("https://api.venice.ai/api/v1/api_keys", headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        return data.get("apiKey"), data.get("id")
    except Exception as e:
        console.print(f"[red]Failed to mint Venice key: {e}[/red]")
        if hasattr(e, 'response') and e.response is not None:
             console.print(f"[red]Response: {e.response.text}[/red]")
        sys.exit(1)

def revoke_venice_key(key_id: str):
    admin_key = os.environ.get("VENICE_ADMIN_KEY")
    if not admin_key or key_id == "fake_key_id":
        return
    
    headers = {"Authorization": f"Bearer {admin_key}"}
    try:
        requests.delete(f"https://api.venice.ai/api/v1/api_keys/{key_id}", headers=headers)
    except Exception as e:
        console.print(f"[yellow]Warning: Failed to revoke key {key_id}: {e}[/yellow]")

@app.command()
def spinup(purpose: str = typer.Argument(..., help="The purpose or specialty of the agent"),
           model: str = typer.Option("glm-5.1", help="The Venice model to use"),
           coordinator: bool = typer.Option(False, help="Create this agent as the coordinator (McOversee)")):
    """Create and start a new Hermes agent"""
    ensure_dirs()
    registry = load_registry()
    
    name = "McOversee" if coordinator else generate_name(registry)
    slug = name.lower()
    
    if name in registry["agents"]:
        console.print(f"[red]Agent {name} already exists.[/red]")
        sys.exit(1)

    console.print(f"[bold green]Spinning up {name}...[/bold green]")
    
    key_val, key_id = mint_venice_key(name, purpose)
    
    # Create profile directory
    profile_dir = PROFILES_DIR / slug
    profile_dir.mkdir(exist_ok=True)
    
    # Write .env
    env_content = f"VENICE_API_KEY={key_val}\nVENICE_BASE_URL=https://api.venice.ai/v1\nWORKSPACE_DIR={WORKSPACE_DIR}\n"
    (profile_dir / ".env").write_text(env_content)
    (profile_dir / ".env").chmod(0o600)
    
    # Write config.yaml
    config = {
        "model": {
            "name": model,
            "provider": "venice"
        },
        "providers": {
            "venice": {
                "base_url": "https://api.venice.ai/v1",
                "api_key_env": "VENICE_API_KEY",
                "protocol": "openai"
            }
        },
        "context_window": 200000 if coordinator else 128000,
        "thinking": "on",
        "tools": {
            "enable": ["all"] if coordinator else ["web_search", "web_extract", "terminal", "read_file", "write_file", "patch", "delegate"],
            "disable": []
        },
        "memory": {
            "enabled": True,
            "compression": "moderate" if coordinator else "aggressive"
        },
        "soul_file": "SOUL.md",
        "memory_file": "MEMORY.md"
    }
    
    if coordinator:
        config["mcp_servers"] = {}
        
    with open(profile_dir / "config.yaml", "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        
    # Write SOUL.md
    if coordinator:
        soul_content = f"""# SOUL.md — {name}

## Identity
You are **{name}**, the coordinator of the McClaw agent fleet.

## Your Job
Delegate subtasks via MCP tool calls to the right agent profiles.
You share a local filesystem with the fleet. Read/write artifacts to `/workspace` instead of passing large texts back to the coordinator.

Do not delegate a task more than twice. If an agent fails, synthesize what you have or complete the task yourself.
"""
    else:
        soul_content = f"""# SOUL.md — {name}

## Identity
You are **{name}**, a Hermes agent specializing in: {purpose}.

You share a local filesystem with the fleet. Read/write artifacts to `/workspace` instead of passing large texts back to the coordinator.
Report results concisely.
"""
    (profile_dir / "SOUL.md").write_text(soul_content)
    
    exec_cmd = "hermes gateway run" if coordinator else "sleep infinity"
    
    # Create Quadlet
    quadlet_content = f"""[Unit]
Description=Hermes Agent {name}

[Container]
Image=localhost/hermes-agent:latest
EnvironmentFile={profile_dir}/.env
Environment=CONTAINER_HOST=unix:///run/podman/podman.sock
Volume={WORKSPACE_DIR}:/workspace:rw
Volume={profile_dir}:/root/.hermes:rw
Volume=/run/user/%U/podman/podman.sock:/run/podman/podman.sock
Exec={exec_cmd}
Network=host

[Install]
WantedBy=default.target
"""
    quadlet_file = QUADLET_DIR / f"{slug}.container"
    quadlet_file.write_text(quadlet_content)
    
    # Reload systemd and start
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "start", slug + ".service"], check=True)
    
    # Update registry
    registry["agents"][name] = {
        "profile": slug,
        "model": model,
        "venice_key_id": key_id,
        "purpose": purpose,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "is_coordinator": coordinator
    }
    registry["used_names"].append(name)
    save_registry(registry)
    
    console.print(f"[bold green]✅ Agent {name} is active![/bold green]")
    console.print(f"Service: systemctl --user status {slug}")

@app.command()
def teardown(name: str):
    """Tear down an existing Hermes agent"""
    registry = load_registry()
    if name not in registry["agents"]:
        console.print(f"[red]Agent {name} not found.[/red]")
        sys.exit(1)
        
    info = registry["agents"][name]
    slug = info["profile"]
    
    console.print(f"[bold yellow]Tearing down {name}...[/bold yellow]")
    
    # Stop and disable systemd
    subprocess.run(["systemctl", "--user", "stop", slug], check=False)
    subprocess.run(["systemctl", "--user", "disable", slug], check=False)
    
    # Remove Quadlet
    quadlet_file = QUADLET_DIR / f"{slug}.container"
    if quadlet_file.exists():
        quadlet_file.unlink()
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    
    # Revoke key
    if info.get("venice_key_id"):
        revoke_venice_key(info["venice_key_id"])
        
    # Remove from registry
    del registry["agents"][name]
    registry["used_names"].remove(name)
    save_registry(registry)
    
    console.print(f"[bold green]✅ Agent {name} completely removed.[/bold green]")

@app.command()
def list():
    """List all active fleet agents"""
    registry = load_registry()
    table = Table(title="Fleet Agents")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Purpose", style="magenta")
    table.add_column("Model", style="green")
    table.add_column("Role", style="blue")
    table.add_column("Status", justify="right")
    
    for name, info in registry["agents"].items():
        slug = info["profile"]
        role = "Coordinator" if info.get("is_coordinator") else "Worker"
        
        try:
            res = subprocess.run(["systemctl", "--user", "is-active", slug], capture_output=True, text=True)
            status = res.stdout.strip()
            status_color = "green" if status == "active" else "red"
            status_fmt = f"[{status_color}]{status}[/{status_color}]"
        except Exception:
            status_fmt = "[red]unknown[/red]"
            
        table.add_row(name, info["purpose"], info["model"], role, status_fmt)
        
    console.print(table)

@app.command()
def logs(name: str, lines: int = typer.Option(50, help="Number of lines to show")):
    """Tail logs for a specific agent"""
    registry = load_registry()
    if name not in registry["agents"]:
        console.print(f"[red]Agent {name} not found.[/red]")
        sys.exit(1)
        
    slug = registry["agents"][name]["profile"]
    subprocess.run(["journalctl", "--user", "-u", slug, "-n", str(lines), "-f"])

@app.command()
def sync_mcp():
    """Update coordinator MCP bridges to include all worker agents"""
    registry = load_registry()
    
    coordinator_name = None
    for name, info in registry["agents"].items():
        if info.get("is_coordinator"):
            coordinator_name = name
            break
            
    if not coordinator_name:
        console.print("[red]No coordinator agent found in registry.[/red]")
        sys.exit(1)
        
    coord_slug = registry["agents"][coordinator_name]["profile"]
    coord_config_file = PROFILES_DIR / coord_slug / "config.yaml"
    
    if not coord_config_file.exists():
        console.print(f"[red]Coordinator config not found at {coord_config_file}[/red]")
        sys.exit(1)
        
    with open(coord_config_file, "r") as f:
        config = yaml.safe_load(f)
        
    mcp_servers = {}
    for name, info in registry["agents"].items():
        if not info.get("is_coordinator"):
            slug = info["profile"]
            # The MCP server is exposed via localhost on a port or via podman.
            # Wait, the quadlet runs `mcp serve`. 
            # How does the coordinator reach the quadlet's MCP server? 
            # If network=host, it binds to a local port. But by default mcp serve runs on stdio.
            # If hermes `mcp serve` supports sse, we can use `http://localhost:.../sse`.
            # Let's assume standard local podman exec or ssh is needed, but wait:
            # The quadlet runs `mcp serve` as its main process. It's expecting stdio.
            # We can connect using podman exec: `podman exec -i {slug} hermes mcp serve`.
            mcp_servers[slug] = {
                "command": "/usr/bin/podman",
                "args": ["--remote", "exec", "-i", f"systemd-{slug}", "hermes", "mcp", "serve"]
            }
            
    config["mcp_servers"] = mcp_servers
    
    with open(coord_config_file, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        
    console.print(f"[bold green]✅ Synced {len(mcp_servers)} worker agents to coordinator {coordinator_name}.[/bold green]")
    console.print(f"Restart coordinator to apply: systemctl --user restart {coord_slug}")

@app.command()
def dashboard():
    """Launch the interactive terminal dashboard"""
    from dashboard import DashboardApp
    DashboardApp().run()

if __name__ == "__main__":
    app()
