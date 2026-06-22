FROM ghcr.io/all-hands-ai/openhands:latest
USER root
# tmux required by RUNTIME=local for shell session management (not in official image)
RUN apt-get update && apt-get install -y tmux && rm -rf /var/lib/apt/lists/*
