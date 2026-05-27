# claude-codex-session-to-html

Automatically save **Claude Code** and **Codex CLI** sessions as searchable HTML chat logs on WSL.

[한국어 문서](./README.ko.md)

## Preview

| Claude Code | Codex CLI |
|---|---|
| Gray header `AI` | Dark header `AI` |
| User messages in yellow bubbles | User messages in yellow bubbles |
| Assistant messages in white bubbles | Assistant messages in white bubbles |
| Expandable tool calls/results | Expandable tool calls/results |

## Features

- Archives Claude Code and Codex CLI sessions to local HTML files.
- Watches live JSONL session updates with `inotifywait`.
- Preserves recent content even if the CLI session is interrupted.
- Renders messages in a chat-style UI with search, dark mode, and collapsible tool logs.
- Keeps existing Claude Code hooks and adds only the required Stop hook.
- Uses only Bash and Python standard library code.

## Requirements

- Windows 11 + WSL2, tested with Ubuntu-style environments
- Python 3.8+
- `inotify-tools` (`install.sh` installs it when missing)
- Claude Code (`claude`) or Codex CLI (`codex`)

## Install

Run the installer from the same WSL user account that runs `claude` or `codex`.

```bash
git clone https://github.com/__YOUR_GITHUB__/claude-codex-session-to-html.git
cd claude-codex-session-to-html
chmod +x install.sh
./install.sh
```

The installer detects your Windows username. If detection fails, it asks you to enter it manually.

Installed scripts are copied to:

```bash
~/.claude/hooks/
```

Do not install only as `root` unless you also run Claude Code or Codex CLI as `root`. The watcher monitors session files under the current WSL user's `$HOME`.

## Output

By default, HTML files are saved to:

```text
C:\Users\<username>\ClaudeSessions\
C:\Users\<username>\CodexSessions\
```

Each session is saved as:

```text
<session-uuid>.html
```

The output path is written into the installed converter scripts during installation. To change it after installing, edit `OUTPUT_DIR` in:

```bash
~/.claude/hooks/session_to_html.py
~/.claude/hooks/codex_to_html.py
```

For example, use `/mnt/d/...` to save logs to a Windows D: drive location.

## How It Works

```text
Claude Code / Codex CLI
  -> writes JSONL session files
  -> session_watcher.sh detects updates
  -> Python converter regenerates HTML
  -> HTML is saved to the Windows output folder
```

Watched session directories:

```bash
$HOME/.claude/projects
$HOME/.codex/sessions
```

Claude Code also gets a Stop hook so the final HTML is regenerated when a session exits normally.

## Manual Conversion

```bash
# Latest Claude Code session
echo '{"session_id":""}' | python3 ~/.claude/hooks/session_to_html.py

# Latest Codex CLI session
echo '{}' | python3 ~/.claude/hooks/codex_to_html.py
```

## Troubleshooting

```bash
# Check watcher
pgrep -f session_watcher.sh && echo "running" || echo "stopped"

# Read logs
tail -f ~/.claude/hooks/watcher.log

# Restart watcher
pkill -f session_watcher.sh
nohup ~/.claude/hooks/session_watcher.sh > ~/.claude/hooks/watcher.log 2>&1 & disown
```

If the watcher is running but a new date/session folder is not being archived, restart the watcher.

## Security

Generated HTML files can contain prompts, local paths, command output, source snippets, tokens, keys, or other sensitive data. Do not commit generated session HTML files or place the output folder in a public/shared location.

## License

MIT
