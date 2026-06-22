FROM ghcr.io/all-hands-ai/openhands:latest
USER root
# tmux required by RUNTIME=local for shell session management
# Playwright chromium required for browser tool support (binaries not bundled in official image)
RUN apt-get update && apt-get install -y tmux && rm -rf /var/lib/apt/lists/*
RUN /app/.venv/bin/playwright install chromium --with-deps
