FROM ghcr.io/all-hands-ai/openhands:latest
USER root
# tmux required by RUNTIME=local for shell session management
# Playwright chromium required for browser tool support (binaries not bundled in official image)
RUN apt-get update && apt-get install -y tmux && rm -rf /var/lib/apt/lists/*
RUN /app/.venv/bin/playwright install chromium --with-deps

# Stub openvscode-server so the VSCode plugin init loop terminates.
# local_runtime.py always sets VSCODE_PORT and the plugin waits for "at"
# in the server output; without this stub it hangs forever on EOF.
RUN mkdir -p /openhands/.openvscode-server/bin && \
    printf '#!/bin/sh\necho "openvscode-server stub at http://localhost:${VSCODE_PORT:-0}"\n' \
      > /openhands/.openvscode-server/bin/openvscode-server && \
    chmod +x /openhands/.openvscode-server/bin/openvscode-server
