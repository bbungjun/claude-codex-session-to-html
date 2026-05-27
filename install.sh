#!/bin/bash
# claude-codex-session-to-html installer
set -e

HOOKS_DIR="$HOME/.claude/hooks"
SETTINGS="$HOME/.claude/settings.json"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║  claude-codex-session-to-html setup  ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── 1. Windows username 입력 ─────────────────────────────────────────────────
WIN_USER=$(cmd.exe /c "echo %USERNAME%" 2>/dev/null | tr -d '\r' || echo "")
if [ -z "$WIN_USER" ]; then
    read -p "Windows username (e.g. young): " WIN_USER
fi
echo "→ Windows user: $WIN_USER"

CLAUDE_OUT="/mnt/c/Users/$WIN_USER/ClaudeSessions"
CODEX_OUT="/mnt/c/Users/$WIN_USER/CodexSessions"

# ── 2. inotify-tools 확인 ────────────────────────────────────────────────────
if ! command -v inotifywait &> /dev/null; then
    echo "→ Installing inotify-tools..."
    sudo apt-get install -y inotify-tools
else
    echo "→ inotify-tools: already installed"
fi

# ── 3. hooks 디렉토리 생성 ───────────────────────────────────────────────────
mkdir -p "$HOOKS_DIR"
mkdir -p "$(dirname "$SETTINGS")"
mkdir -p "$CLAUDE_OUT"
mkdir -p "$CODEX_OUT"
echo "→ Output dirs created"

# ── 4. 스크립트 복사 & 경로 치환 ────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)/hooks"

sed "s|__USERNAME__|$WIN_USER|g" "$SCRIPT_DIR/session_to_html.py" > "$HOOKS_DIR/session_to_html.py"
sed "s|__USERNAME__|$WIN_USER|g" "$SCRIPT_DIR/codex_to_html.py"   > "$HOOKS_DIR/codex_to_html.py"
cp  "$SCRIPT_DIR/session_watcher.sh"                               "$HOOKS_DIR/session_watcher.sh"

chmod +x "$HOOKS_DIR/session_to_html.py"
chmod +x "$HOOKS_DIR/codex_to_html.py"
chmod +x "$HOOKS_DIR/session_watcher.sh"
echo "→ Scripts installed to $HOOKS_DIR"

# ── 5. Claude Code Stop hook 등록 ───────────────────────────────────────────
if [ -f "$SETTINGS" ]; then
    python3 - << PYEOF
import json
from pathlib import Path

settings_path = Path('$SETTINGS')
hook_command = 'python3 $HOOKS_DIR/session_to_html.py'

with settings_path.open() as f:
    d = json.load(f)

hooks = d.setdefault('hooks', {})
if not isinstance(hooks, dict):
    hooks = {}
    d['hooks'] = hooks

stop_hooks = hooks.setdefault('Stop', [])
if not isinstance(stop_hooks, list):
    stop_hooks = []
    hooks['Stop'] = stop_hooks

already_installed = any(
    isinstance(group, dict)
    and any(
        isinstance(hook, dict) and hook.get('command') == hook_command
        for hook in group.get('hooks', [])
    )
    for group in stop_hooks
)

if not already_installed:
    stop_hooks.append({
        'matcher': '',
        'hooks': [{'type': 'command', 'command': hook_command}],
    })

with settings_path.open('w') as f:
    json.dump(d, f, indent=2)
PYEOF
    echo "→ Claude Stop hook merged into existing settings.json"
else
    cat > "$SETTINGS" << EOF
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 $HOOKS_DIR/session_to_html.py"
          }
        ]
      }
    ]
  }
}
EOF
    echo "→ settings.json created"
fi

# ── 6. .bashrc 자동 시작 추가 ───────────────────────────────────────────────
BASHRC="$HOME/.bashrc"
MARKER_START="# claude-codex-session-to-html start"
MARKER_END="# claude-codex-session-to-html end"

touch "$BASHRC"
python3 - << PYEOF
from pathlib import Path

bashrc = Path('$BASHRC')
start = '$MARKER_START'
end = '$MARKER_END'
block = f'''
{start}
if ! pgrep -f "session_watcher.sh" > /dev/null 2>&1; then
    nohup $HOOKS_DIR/session_watcher.sh > $HOOKS_DIR/watcher.log 2>&1 &
    disown
fi
{end}
'''.strip()

text = bashrc.read_text()
if start in text and end in text:
    before = text[:text.index(start)].rstrip()
    after = text[text.index(end) + len(end):].lstrip()
    pieces = [p for p in (before, block, after) if p]
    text = '\n\n'.join(pieces) + '\n'
elif '# claude-codex-session-saver start' in text and '# claude-codex-session-saver end' in text:
    old_start = '# claude-codex-session-saver start'
    old_end = '# claude-codex-session-saver end'
    before = text[:text.index(old_start)].rstrip()
    after = text[text.index(old_end) + len(old_end):].lstrip()
    pieces = [p for p in (before, block, after) if p]
    text = '\n\n'.join(pieces) + '\n'
elif '# cli-session-saver' in text:
    lines = text.splitlines()
    marker_index = next(i for i, line in enumerate(lines) if line.strip() == '# cli-session-saver')
    before = '\n'.join(lines[:marker_index]).rstrip()
    after_index = marker_index + 1
    if after_index < len(lines) and 'pgrep -f "session_watcher.sh"' in lines[after_index]:
        after_index += 1
        while after_index < len(lines):
            line = lines[after_index].strip()
            after_index += 1
            if line == 'fi':
                break
    after = '\n'.join(lines[after_index:]).lstrip()
    pieces = [p for p in (before, block, after) if p]
    text = '\n\n'.join(pieces) + '\n'
else:
    text = text.rstrip()
    text = (text + '\n\n' if text else '') + block + '\n'

bashrc.write_text(text)
PYEOF
echo "→ Auto-start configured in .bashrc"

# ── 7. 즉시 watcher 시작 ────────────────────────────────────────────────────
pkill -f session_watcher.sh 2>/dev/null || true
nohup "$HOOKS_DIR/session_watcher.sh" > "$HOOKS_DIR/watcher.log" 2>&1 &
disown
sleep 1

echo ""
echo "╔══════════════════════════════════════╗"
echo "║          Installation complete!      ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "  Claude sessions → C:\\Users\\$WIN_USER\\ClaudeSessions\\"
echo "  Codex  sessions → C:\\Users\\$WIN_USER\\CodexSessions\\"
echo ""
pgrep -f session_watcher.sh > /dev/null && echo "  ✅ Watcher is running" || echo "  ❌ Watcher failed to start"
echo ""
