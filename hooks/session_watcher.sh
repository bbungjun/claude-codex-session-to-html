#!/bin/bash
# claude-codex-session-to-html: File watcher daemon
# Monitors Claude Code and Codex CLI session files and converts them to HTML on change.

CLAUDE_DIR="$HOME/.claude/projects"
CODEX_DIR="$HOME/.codex/sessions"
DEBOUNCE=1  # seconds

echo "[watcher] started"
echo "[watcher] Claude: $CLAUDE_DIR"
echo "[watcher] Codex:  $CODEX_DIR"

if ! command -v inotifywait &> /dev/null; then
    echo "[watcher] ERROR: inotify-tools not found."
    echo "[watcher] Install: sudo apt install inotify-tools"
    exit 1
fi

WATCH_DIRS=()
if [ -d "$CLAUDE_DIR" ]; then
    WATCH_DIRS+=("$CLAUDE_DIR")
else
    echo "[watcher] Claude directory not found; skipping."
fi
if [ -d "$CODEX_DIR" ]; then
    WATCH_DIRS+=("$CODEX_DIR")
else
    echo "[watcher] Codex directory not found; skipping."
fi

if [ ${#WATCH_DIRS[@]} -eq 0 ]; then
    echo "[watcher] No session directories found. Exiting."
    exit 1
fi

last_claude_triggered=0
last_codex_triggered=0

inotifywait -m -r -e close_write,create,modify,moved_to "${WATCH_DIRS[@]}" --format '%w%f' 2>/dev/null | \
while read -r filepath; do
    [[ "$filepath" != *.jsonl ]] && continue

    now=$(date +%s)

    if [[ "$filepath" == *"/.claude/"* ]]; then
        diff=$((now - last_claude_triggered))
        [ "$diff" -lt "$DEBOUNCE" ] && continue
        last_claude_triggered=$now
        echo "[watcher] Claude → $filepath"
        printf '{"session_id":"","session_file":%s}\n' "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$filepath")" | python3 "$(dirname "$0")/session_to_html.py"
    elif [[ "$filepath" == *"/.codex/"* ]]; then
        diff=$((now - last_codex_triggered))
        [ "$diff" -lt "$DEBOUNCE" ] && continue
        last_codex_triggered=$now
        echo "[watcher] Codex  → $filepath"
        printf '{"session_file":%s}\n' "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$filepath")" | python3 "$(dirname "$0")/codex_to_html.py"
    fi
done
