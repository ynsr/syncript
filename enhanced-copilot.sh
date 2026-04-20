copilot() {
  if [ -z "$TMUX" ]; then
    echo "Error: not inside a tmux session." >&2
    echo "" >&2
    echo "tmux quick primer:" >&2
    echo "  tmux new -s copilot      # Create a named session" >&2
    echo "  tmux attach -t copilot   # Re-attach after disconnecting" >&2
    echo "  Ctrl+B, D                # Detach (leave it running in background)" >&2
    echo "  tmux ls                  # List active sessions" >&2
    return 1
  fi
  # command copilot --autopilot --model claude-sonnet-4.5 "$@"
  command copilot --autopilot --model gpt-5.3-codex "$@"
}
