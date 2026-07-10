#!/usr/bin/env python3
"""Auto-name herdr agents and workspaces, ChatGPT-style.

- Agents are renamed to their Claude Code session title (the ``firstPrompt``
  shown in ``claude --resume``) whenever a turn ends (status -> idle).
- Workspaces are renamed to the basename of the live working directory
  (``foreground_cwd``) of their panes, majority vote, focused pane breaks ties.
- Manual renames are respected: once a name differs from what this plugin
  recorded, that agent/workspace is never touched again.
"""
import glob
import json
import os
import re
import subprocess
import time

STATE_DIR = os.environ.get("HERDR_PLUGIN_CONFIG_DIR") or os.path.expanduser(
    "~/.config/herdr/plugins/config/auto-namer"
)


def load_config():
    defaults = {
        "rename_agents": True,
        "rename_workspaces": True,
        "max_len": 40,
        "mtime_window": 20,
    }
    try:
        with open(os.path.join(STATE_DIR, "config.json")) as f:
            defaults.update(json.load(f))
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return defaults


CFG = load_config()
MTIME_WINDOW = float(os.environ.get("AUTO_NAMER_MTIME_WINDOW", CFG["mtime_window"]))
MAX_LEN = int(CFG["max_len"])


def herdr(*args):
    try:
        r = subprocess.run(["herdr", *args], capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return None
        return json.loads(r.stdout)["result"]
    except Exception:
        return None


def read_state(key):
    try:
        with open(os.path.join(STATE_DIR, key)) as f:
            return f.read()
    except OSError:
        return ""


def write_state(key, val):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(os.path.join(STATE_DIR, key), "w") as f:
        f.write(val)


def project_dir(cwd):
    """Map a working directory to its Claude Code project directory."""
    return os.path.expanduser("~/.claude/projects/" + re.sub(r"[^A-Za-z0-9]", "-", cwd))


def find_session_path(agent):
    """Return the agent's session transcript path.

    Prefers the session reported through herdr's agent integration
    (``herdr integration install claude``). Falls back to mtime correlation:
    the transcript written moments before the idle transition is this pane's
    session. Skips when ambiguous (several sessions active in the same dir).
    """
    cwd = agent.get("cwd") or ""
    sess = agent.get("agent_session") or {}
    value = sess.get("value") or sess.get("path") or agent.get("agent_session_path")
    if value:
        # kind == "path": transcript path; kind == "id": session uuid
        if sess.get("kind") == "id" and cwd:
            path = os.path.join(project_dir(cwd), value + ".jsonl")
        else:
            path = value
        if os.path.exists(path):
            return path
    if not cwd:
        return None
    now = time.time()
    recent = [
        p for p in glob.glob(project_dir(cwd) + "/*.jsonl")
        if now - os.path.getmtime(p) < MTIME_WINDOW
    ]
    return recent[0] if len(recent) == 1 else None


def session_title(session_path):
    """Return the session title as shown in the ``claude --resume`` picker."""
    session_id = os.path.splitext(os.path.basename(session_path))[0]
    index = os.path.join(os.path.dirname(session_path), "sessions-index.json")
    try:
        for e in json.load(open(index)).get("entries", []):
            if e.get("sessionId") == session_id and e.get("firstPrompt"):
                return e["firstPrompt"]
    except (OSError, json.JSONDecodeError):
        pass
    # Index is updated lazily; fall back to the first substantive user
    # message in the transcript.
    first_command = None
    try:
        with open(session_path) as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") != "user" or rec.get("isMeta"):
                    continue
                content = (rec.get("message") or {}).get("content")
                if isinstance(content, list):
                    content = next(
                        (c.get("text") for c in content if isinstance(c, dict) and c.get("type") == "text"), ""
                    )
                if not isinstance(content, str) or not content.strip():
                    continue
                # Slash-command records are noise; keep the command name only
                # as a last resort.
                if "<command-name>" in content:
                    if first_command is None:
                        m = re.search(r"<command-name>(.*?)</command-name>", content)
                        first_command = m.group(1).strip() if m else None
                    continue
                if "<local-command-stdout>" in content or content.lstrip().startswith("Caveat:"):
                    continue
                return content
    except OSError:
        pass
    return first_command


def clean_title(raw):
    title = " ".join(raw.split())
    return title[:MAX_LEN] if title else None


def rename_agent(pane_id):
    info = herdr("agent", "get", pane_id)
    if not info:
        return
    agent = info.get("agent") or {}
    slug = pane_id.replace(":", "_")
    current = agent.get("name") or ""
    path = find_session_path(agent)
    if not path:
        return
    session_id = os.path.splitext(os.path.basename(path))[0]
    # Manual renames are respected within a session, but a session change
    # always re-adopts the pane: the name follows the session.
    recorded_session = read_state("agent_" + slug + ".session")
    recorded_name = read_state("agent_" + slug + ".name")
    if current and session_id == recorded_session and current != recorded_name:
        return  # renamed manually during this session — leave it alone
    raw = session_title(path)
    title = clean_title(raw) if raw else None
    if not title:
        return
    if title != current and herdr("agent", "rename", pane_id, title) is None:
        return
    write_state("agent_" + slug + ".name", title)
    write_state("agent_" + slug + ".session", session_id)


def rename_workspace(ws_id):
    ws = herdr("workspace", "get", ws_id)
    if not ws:
        return
    current = (ws.get("workspace") or ws).get("label") or ""
    panes = (herdr("pane", "list", "--workspace", ws_id) or {}).get("panes") or []
    if not panes:
        return
    # Majority vote over live working directories; focused pane breaks ties.
    counts = {}
    focused_label = None
    for p in panes:
        cwd = p.get("foreground_cwd") or p.get("cwd") or ""
        if not cwd:
            continue
        base = os.path.basename(cwd.rstrip("/"))
        counts[base] = counts.get(base, 0) + 1
        if p.get("focused"):
            focused_label = base
    if not counts:
        return
    best = max(counts.values())
    top = [b for b, c in counts.items() if c == best]
    label = focused_label if focused_label in top else top[0]
    if not label or label == current:
        return
    key = "ws_" + ws_id + ".name"
    recorded = read_state(key)
    if recorded and current != recorded:
        return  # renamed manually after adoption — leave it alone
    if herdr("workspace", "rename", ws_id, label) is not None:
        write_state(key, label)


def main():
    event = os.environ.get("HERDR_PLUGIN_EVENT", "")
    data = json.loads(os.environ.get("HERDR_PLUGIN_EVENT_JSON", "{}")).get("data", {})
    pane_id = data.get("pane_id") or ""
    ws_id = data.get("workspace_id") or (pane_id.split(":")[0] if ":" in pane_id else "")

    if CFG["rename_agents"] and event == "pane.agent_status_changed":
        if (data.get("agent_status") or "").lower() == "idle" and pane_id:
            rename_agent(pane_id)
    if CFG["rename_workspaces"] and ws_id:
        rename_workspace(ws_id)


if __name__ == "__main__":
    main()
