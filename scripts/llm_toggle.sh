#!/usr/bin/env bash
# Toggle this Mac's availability as PikaRAG's local LLM host: brings
# Tailscale + Ollama up together, or takes them both down together.
# Tailscale is toggled here (not left always-on) because this project is
# the only thing on this Mac that uses it -- see docs/DEPLOYMENT.md
# section 3. The live bot already degrades gracefully (existing
# CircuitBreaker + offline message) when this host is unreachable, so
# turning this off requires no other action anywhere.
set -euo pipefail

usage() {
  echo "Usage: $0 {on|off|status}" >&2
  exit 1
}

[ $# -eq 1 ] || usage

case "$1" in
  on)
    tailscale up
    open -a Ollama
    echo "Tailscale up, Ollama launching."
    ;;
  off)
    # osascript's "quit app" doesn't reliably work on Ollama (a
    # menu-bar-only app with no standard Quit menu handler) -- kill the
    # processes directly instead, same fix used earlier in this project
    # when a plain menu-bar Quit also failed to fully stop it.
    pkill -x Ollama 2>/dev/null || true
    pkill -x ollama 2>/dev/null || true
    tailscale down
    echo "Ollama killed, Tailscale down."
    ;;
  status)
    echo "--- Tailscale ---"
    tailscale status --self 2>&1 | head -1 || true
    echo "--- Ollama ---"
    if pgrep -x ollama >/dev/null 2>&1; then
      echo "running"
    else
      echo "not running"
    fi
    ;;
  *)
    usage
    ;;
esac
