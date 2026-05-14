FROM ubuntu:24.04

RUN apt-get update && apt-get install -y \
    curl \
    jq \
    bash \
    python3 \
    python3-venv \
    python3-pip \
    git \
    podman \
    && rm -rf /var/lib/apt/lists/*

# Install Hermes Agent
RUN curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash

# Ensure hermes is in PATH
ENV PATH="/usr/local/bin:/root/.local/bin:$PATH"

# Create a shared workspace mount point
RUN mkdir -p /workspace

WORKDIR /workspace
