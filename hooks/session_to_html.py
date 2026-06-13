#!/usr/bin/env python3
"""
Claude Code Session → HTML Converter
Converts ~/.claude/projects/**/*.jsonl to a KakaoTalk-style HTML chat UI.
"""
import json, sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if (REPO_ROOT / "session_memory").is_dir():
    sys.path.insert(0, str(REPO_ROOT))

try:
    from session_memory.indexer import index_session
except ImportError:
    index_session = None

# ── Config ──────────────────────────────────────────────────────────────────
OUTPUT_DIR      = Path.home() / "session_history"
MAX_TOOL_CONTENT = 500
MAX_BUBBLE_TEXT  = 2000
# ────────────────────────────────────────────────────────────────────────────

def log(msg):
    print(f"[claude-logger] {msg}", file=sys.stderr)

try:
    hook_data  = json.loads(sys.stdin.read() or "{}")
    session_id = hook_data.get("session_id", "")
    session_file = hook_data.get("session_file", "")
except json.JSONDecodeError as exc:
    log(f"invalid stdin payload: {exc}")
    session_id = ""
    session_file = ""

projects_dir = Path.home() / ".claude" / "projects"
jsonl_files  = list(projects_dir.rglob("*.jsonl"))
target_file = Path(session_file).expanduser() if session_file else None

if target_file and (not target_file.is_file() or target_file.suffix != ".jsonl"):
    log(f"session_file is not a JSONL file: {target_file}")
    sys.exit(1)

if not target_file and not jsonl_files:
    sys.exit(0)

if not target_file and session_id:
    for f in jsonl_files:
        if session_id in f.name:
            target_file = f
            break
if not target_file:
    target_file = max(jsonl_files, key=lambda f: f.stat().st_mtime)

def esc(t):
    return str(t).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace("\n","<br>")

def long_text(txt, limit=MAX_BUBBLE_TEXT):
    if len(txt) <= limit:
        return txt
    return f'{txt[:limit]}<details class="more"><summary>…더 보기</summary>{txt[limit:]}</details>'

def format_tool_input(name, inp):
    if not isinstance(inp, dict):
        return f"<code>{esc(str(inp)[:MAX_TOOL_CONTENT])}</code>"
    path        = inp.get("file_path") or inp.get("path") or inp.get("filePath","")
    content     = inp.get("content","") or inp.get("new_content","")
    command     = inp.get("command","")
    description = inp.get("description","")
    old_str     = inp.get("old_string","") or inp.get("old_str","")
    new_str     = inp.get("new_string","") or inp.get("new_str","")
    parts = []
    if path:        parts.append(f'<span class="ti-path">📄 {esc(path)}</span>')
    if command:     parts.append(f'<span class="ti-cmd">$ {esc(command[:200])}</span>')
    if description: parts.append(f'<span class="ti-desc">{esc(description[:200])}</span>')
    if old_str:
        p = old_str[:MAX_TOOL_CONTENT]
        parts.append(f'<div class="ti-diff"><span class="diff-label">변경 전</span><code>{esc(p)}{"…" if len(old_str)>MAX_TOOL_CONTENT else ""}</code></div>')
    if new_str:
        p = new_str[:MAX_TOOL_CONTENT]
        parts.append(f'<div class="ti-diff"><span class="diff-label add">변경 후</span><code>{esc(p)}{"…" if len(new_str)>MAX_TOOL_CONTENT else ""}</code></div>')
    if content and not old_str:
        p = content[:MAX_TOOL_CONTENT]
        parts.append(f'<div class="ti-content"><code>{esc(p)}{"…" if len(content)>MAX_TOOL_CONTENT else ""}</code></div>')
    if not parts:
        raw = json.dumps(inp, ensure_ascii=False)[:MAX_TOOL_CONTENT]
        parts.append(f'<code>{esc(raw)}</code>')
    return "".join(parts)

# ── Parse JSONL ──────────────────────────────────────────────────────────────
messages = []
parse_errors = 0
with open(target_file, "r", encoding="utf-8") as f:
    for line_no, line in enumerate(f, 1):
        line = line.strip()
        if not line: continue
        try:
            obj = json.loads(line)
            msg_type = obj.get("type","")
            ts = obj.get("timestamp","")
            if msg_type == "user":
                content = obj.get("message",{}).get("content","")
                if isinstance(content, list):
                    texts, tool_results = [], []
                    for c in content:
                        if c.get("type") == "text":
                            texts.append(c.get("text",""))
                        elif c.get("type") == "tool_result":
                            tr = c.get("content","")
                            if isinstance(tr, list):
                                tr = " ".join(x.get("text","") for x in tr if x.get("type")=="text")
                            tool_results.append(str(tr).strip())
                    text = " ".join(texts).strip()
                    if not text and tool_results:
                        messages.append({"role":"tool_result","results":tool_results,"ts":ts})
                        continue
                else:
                    text = str(content)
                if text.strip():
                    messages.append({"role":"user","text":text.strip(),"ts":ts})
            elif msg_type == "assistant":
                blocks = obj.get("message",{}).get("content",[])
                if isinstance(blocks, str):
                    blocks = [{"type":"text","text":blocks}]
                texts, tools = [], []
                for b in blocks:
                    if b.get("type")=="text": texts.append(b.get("text",""))
                    elif b.get("type")=="tool_use": tools.append({"name":b.get("name","tool"),"input":b.get("input",{})})
                combined = "\n".join(texts).strip()
                if combined or tools:
                    messages.append({"role":"assistant","text":combined,"tools":tools,"ts":ts})
        except (json.JSONDecodeError, AttributeError, TypeError) as exc:
            parse_errors += 1
            if parse_errors <= 3:
                log(f"skipped malformed line {line_no}: {exc}")

if parse_errors:
    log(f"skipped {parse_errors} malformed line(s) in {target_file}")

if not messages:
    sys.exit(0)

# ── Build HTML ───────────────────────────────────────────────────────────────
project_name = target_file.parent.name
session_date = datetime.now().strftime("%Y-%m-%d %H:%M")
session_uuid = target_file.stem

parts = []
for m in messages:
    ts_raw    = m.get("ts","")
    time_only = ts_raw[11:16] if len(ts_raw) >= 16 else ts_raw
    role      = m["role"]

    if role == "user":
        txt = long_text(esc(m["text"]))
        parts.append(
            f'<div class="row ur" data-role="user"><div class="ts-out">{time_only}</div>'
            f'<div class="bbl ub">{txt}</div></div>'
        )
    elif role == "assistant":
        txt   = long_text(esc(m.get("text","")))
        tools = m.get("tools",[])
        tool_html = "".join(
            f'<details class="tool-detail"><summary><span class="tb">⚙ {esc(t["name"])}</span></summary>'
            f'<div class="tool-body">{format_tool_input(t["name"],t["input"])}</div></details>'
            for t in tools
        )
        body = txt if txt else ""
        parts.append(
            f'<div class="row ar" data-role="assistant"><div class="av aa">AI</div>'
            f'<div class="msg-wrap"><div class="sender-name">Claude</div>'
            f'<div class="bubble-ts-row"><div class="bbl ab">{body}{tool_html}</div>'
            f'<div class="ts-out">{time_only}</div></div></div></div>'
        )
    elif role == "tool_result":
        for res in m.get("results",[]):
            if not res or len(res) < 5: continue
            preview = esc(res[:MAX_TOOL_CONTENT]) + ("…" if len(res)>MAX_TOOL_CONTENT else "")
            parts.append(
                f'<div class="row ar tool-result-row" data-role="tool"><div class="av sr-av">↩</div>'
                f'<div class="msg-wrap"><div class="sender-name" style="color:#999">tool result</div>'
                f'<div class="bubble-ts-row"><div class="bbl sb">'
                f'<details><summary>내용 보기</summary><div class="tool-body"><code>{preview}</code></div></details></div>'
                f'<div class="ts-out">{time_only}</div></div></div></div>'
            )

bubbles = "".join(parts)

HTML_TEMPLATE = """<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Claude Session · {session_date}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{--bg:#d7dee5;--panel:#4b5563;--panel-2:#374151;--text:#172033;--muted:#667085;--line:#c9d3df;--ai:#ffffff;--user:#ffe55c;--tool:#edf2f7;--accent:#f8fafc;--shadow:0 10px 30px rgba(21,32,48,.12)}}
body.dark{{--bg:#111827;--panel:#0b1120;--panel-2:#172033;--text:#e5e7eb;--muted:#9ca3af;--line:#263244;--ai:#1f2937;--user:#d7b500;--tool:#111827;--accent:#7dd3fc;--shadow:none}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Malgun Gothic','Apple SD Gothic Neo',sans-serif;background:var(--bg);color:var(--text);display:flex;flex-direction:column;height:100vh;font-size:14px;letter-spacing:0}}
header{{background:var(--panel);color:#fff;padding:14px 18px 10px;border-bottom:1px solid var(--panel-2);box-shadow:var(--shadow);position:sticky;top:0;z-index:10}}
.topbar{{display:flex;align-items:center;gap:12px;min-width:0}}
.hi{{width:38px;height:38px;border-radius:10px;background:var(--panel-2);display:flex;align-items:center;justify-content:center;font-size:17px;color:#fff;flex-shrink:0}}
.ht{{min-width:0}}.ht h2{{font-size:15px;color:#fff;font-weight:700;line-height:1.25}}.ht p{{font-size:11px;color:#d1d5db;margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:52vw}}
.badge{{margin-left:auto;background:var(--panel-2);color:#fff;font-size:11px;padding:5px 10px;border-radius:999px;white-space:nowrap}}
.controls{{display:grid;grid-template-columns:minmax(180px,1fr) auto auto auto;gap:8px;margin-top:12px}}
.search{{width:100%;height:34px;border:1px solid #d0d5dd;background:#fff;color:#111827;border-radius:8px;padding:0 11px;font-size:13px;outline:none}}
body.dark .search{{background:#0f172a;color:#e5e7eb;border-color:#334155}}
.btn{{height:34px;border:1px solid rgba(255,255,255,.22);background:var(--panel-2);color:#f8fafc;border-radius:8px;padding:0 10px;font-size:12px;cursor:pointer;white-space:nowrap}}
.btn:hover{{border-color:#fff;color:#fff}}
.chat{{flex:1;overflow-y:auto;padding:18px 14px 20px;display:flex;flex-direction:column;gap:8px;contain:layout style}}
.row{{display:flex;align-items:flex-start;gap:9px;max-width:min(82%,760px)}}
.row.is-hidden{{display:none}}
.ur{{align-self:flex-end;flex-direction:row-reverse;max-width:min(76%,700px)}}.ar{{align-self:flex-start}}
.av{{width:36px;height:36px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:800;flex-shrink:0;margin-top:2px}}
.aa{{background:var(--panel-2);color:#fff}}
.sr-av{{background:#98a2b3;color:#fff;font-size:13px;width:36px;height:36px;border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:2px}}
.msg-wrap{{display:flex;flex-direction:column;gap:4px;min-width:0}}
.sender-name{{font-size:11px;color:var(--muted);margin-left:2px;font-weight:600}}
.bubble-ts-row{{display:flex;align-items:flex-end;gap:6px;min-width:0}}
.bbl{{padding:10px 13px;border-radius:14px;max-width:680px;line-height:1.65;word-break:break-word;white-space:pre-wrap;font-size:14px;contain:content;box-shadow:0 1px 1px rgba(15,23,42,.08)}}
.ub{{background:var(--user);color:#1a1a1a;border-radius:14px 14px 3px 14px}}
.ab{{background:var(--ai);color:var(--text);border-radius:3px 14px 14px 14px;border:1px solid rgba(148,163,184,.25)}}
.sb{{background:var(--tool);color:var(--muted);border-radius:10px;font-size:12px;border:1px solid rgba(148,163,184,.25)}}
.ts-out{{font-size:10px;color:var(--muted);white-space:nowrap;align-self:flex-end;padding-bottom:3px}}
.tb{{display:inline-block;margin:3px 3px 0 0;background:#eef2f7;color:#475467;font-size:11px;padding:3px 8px;border-radius:8px;cursor:pointer;border:1px solid #d0d5dd}}
body.dark .tb{{background:#111827;color:#cbd5e1;border-color:#334155}}
details.tool-detail{{margin-top:5px}}
details summary{{list-style:none;cursor:pointer;outline:none}}
details summary::-webkit-details-marker{{display:none}}
details[open] summary .tb{{background:#dbeafe;border-color:#93c5fd;color:#1d4ed8}}
.tool-body{{margin-top:7px;padding:9px 10px;background:rgba(148,163,184,.12);border-radius:8px;border:1px solid rgba(148,163,184,.28);font-size:11px;line-height:1.6;white-space:normal}}
.ti-path{{color:#1a73e8;display:block;margin-bottom:3px;font-weight:700}}
.ti-cmd{{color:#c0392b;display:block;margin-bottom:3px;font-family:ui-monospace,SFMono-Regular,Consolas,monospace}}
.ti-desc{{color:var(--muted);display:block;margin-bottom:3px}}
.diff-label{{font-size:10px;color:#e05252;margin-right:4px;font-weight:700}}.diff-label.add{{color:#27ae60}}
.ti-content code,.ti-diff code{{display:block;color:var(--text);font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11px;white-space:pre-wrap;margin-top:3px;max-height:220px;overflow-y:auto;background:rgba(15,23,42,.06);padding:6px 7px;border-radius:6px}}
details.more summary{{color:#1a73e8;font-size:12px;cursor:pointer;margin-top:4px}}
.tool-result-row{{opacity:.78}}
footer{{text-align:center;padding:8px 12px;font-size:10px;color:#d1d5db;background:var(--panel);border-top:1px solid var(--panel-2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
::-webkit-scrollbar{{width:7px}}::-webkit-scrollbar-track{{background:transparent}}::-webkit-scrollbar-thumb{{background:#94a3b8;border-radius:999px}}
@media (max-width:720px){{.controls{{grid-template-columns:1fr 1fr}}.search{{grid-column:1 / -1}}.badge{{display:none}}.row,.ur{{max-width:94%}}.ht p{{max-width:68vw}}.bbl{{max-width:100%}}}}
</style></head><body>
<header>
  <div class="topbar">
    <div class="hi">🤖</div>
    <div class="ht"><h2>Claude Code Session</h2><p>{project_name}</p></div>
    <span class="badge" id="countBadge">{msg_count}개 메시지 · {session_date}</span>
  </div>
  <div class="controls">
    <input class="search" id="search" type="search" placeholder="대화 검색">
    <button class="btn" id="toggleTools" type="button">툴 숨김</button>
    <button class="btn" id="toggleDetails" type="button">모두 펼침</button>
    <button class="btn" id="toggleTheme" type="button">다크</button>
  </div>
</header>
<div class="chat" id="chat">{bubbles}</div>
<footer>{filename}</footer>
<script>
(() => {{
  const chat = document.getElementById('chat');
  const rows = Array.from(document.querySelectorAll('.row'));
  const search = document.getElementById('search');
  const toolBtn = document.getElementById('toggleTools');
  const detailBtn = document.getElementById('toggleDetails');
  const themeBtn = document.getElementById('toggleTheme');
  let showTools = true;
  let detailsOpen = false;
  const savedTheme = localStorage.getItem('cli-session-theme');
  if (savedTheme === 'dark') document.body.classList.add('dark');
  themeBtn.textContent = document.body.classList.contains('dark') ? '라이트' : '다크';
  function applyFilters() {{
    const q = search.value.trim().toLowerCase();
    rows.forEach(row => {{
      const isTool = row.dataset.role === 'tool';
      const matches = !q || row.textContent.toLowerCase().includes(q);
      row.classList.toggle('is-hidden', (isTool && !showTools) || !matches);
    }});
  }}
  search.addEventListener('input', applyFilters);
  toolBtn.addEventListener('click', () => {{
    showTools = !showTools;
    toolBtn.textContent = showTools ? '툴 숨김' : '툴 표시';
    applyFilters();
  }});
  detailBtn.addEventListener('click', () => {{
    detailsOpen = !detailsOpen;
    document.querySelectorAll('details').forEach(d => d.open = detailsOpen);
    detailBtn.textContent = detailsOpen ? '모두 접기' : '모두 펼침';
  }});
  themeBtn.addEventListener('click', () => {{
    document.body.classList.toggle('dark');
    const dark = document.body.classList.contains('dark');
    localStorage.setItem('cli-session-theme', dark ? 'dark' : 'light');
    themeBtn.textContent = dark ? '라이트' : '다크';
  }});
  requestAnimationFrame(() => {{ chat.scrollTop = chat.scrollHeight; }});
}})();
</script>
</body></html>"""

html = HTML_TEMPLATE.format(
    session_date=session_date,
    project_name=esc(project_name),
    msg_count=len(messages),
    bubbles=bubbles,
    filename=target_file.name,
)

try:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = OUTPUT_DIR / f"{session_uuid}.html"
    out_file.write_text(html, encoding="utf-8")
    if index_session:
        try:
            index_session("claude", target_file, out_file, OUTPUT_DIR / "index.sqlite")
        except Exception as exc:
            log(f"failed to update index: {exc}")
except OSError as exc:
    log(f"failed to write HTML: {exc}")
    sys.exit(1)

log(f"saved → {out_file}")
