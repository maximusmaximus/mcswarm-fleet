# Hermes Fleet Manager

A robust, feature-rich CLI for deploying, orchestrating, and tearing down local fleets of [Hermes Agents](https://github.com/NousResearch/hermes-agent) using **Podman** and **Systemd Quadlets**. 

Instead of manual scripts, this CLI provides a clean, declarative interface for spinning up multi-agent workflows. It automatically configures isolated agent containers, securely mints Venice.ai API keys on the fly, dynamically wires them together via the MCP (Model Context Protocol) standard, and establishes a shared filesystem workspace.

## Features

- **Podman Quadlets:** Deploys agents as rootless Systemd user services (`systemctl --user`), ensuring they survive host reboots and are fully managed by the OS.
- **Shared Workspace:** All agents mount a common `/workspace` volume, allowing them to instantly collaborate on code and artifacts without polluting token windows.
- **Dynamic MCP Bridging:** Automatically wires worker agents into the coordinator's toolset. The coordinator spawns isolated `hermes mcp serve` processes inside the worker containers via `podman exec`.
- **API Key Lifecycle:** Automatically mints and revokes Venice.ai keys when agents are created or destroyed.

## Setup & Installation

### Prerequisites
- Python 3.10+
- Podman
- systemd (running as user)
- An active Venice.ai Admin API Key

```bash
export VENICE_ADMIN_KEY="your-admin-key"
```

### Installation
```bash
git clone https://github.com/yourusername/mcswarm-fleet.git
cd mcswarm-fleet
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Building the Base Image
Before spinning up agents, build the base agent container image:

```bash
cd agent-image
podman build -t hermes-agent:latest .
```

## Usage

```bash
# Spin up a worker agent specialized in Python debugging
python main.py spinup "Python debug and triage" --model glm-5.1

# Spin up a creative writer worker
python main.py spinup "Creative Writing" --model venice-uncensored-1.2

# Spin up the coordinator agent (McOversee)
python main.py spinup "Coordination" --coordinator

# Link the worker agents to the coordinator
python main.py sync-mcp

# See the status of the entire fleet
python main.py list

# View logs for a specific agent
python main.py logs McMuse

# Tear down an agent and revoke its API key
python main.py teardown McMuse
```
