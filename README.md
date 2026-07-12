# herdr-auto-namer

ChatGPT-style automatic naming for [herdr](https://herdr.dev): agents are named
after their Claude Code **session title**, workspaces after their **working
directory** — no more sidebar full of identical `claude` rows.

| Before | After |
| --- | --- |
| `nvim · claude` | `chat · fix launcher visibility` |
| `nvim · claude` | `chat · migrate widget to snacks` |
| `rails · claude` | `rails · add UI tests` |

## What it does

- **Agents** — when a turn ends (agent goes `idle`), the pane's agent is
  renamed after what it is working on. Two modes:
  - **`llm`** (default) — recent pane output is summarized by `claude` (haiku)
    into one complete phrase of at most 12 characters, in the language of the
    output. Names evolve as the task moves on; at most one rename per pane
    every 3 minutes. Works for any agent whose pane herdr can read.
  - **`session`** — the name is the Claude Code session title: the same
    `firstPrompt` you see in the `claude --resume` picker. Stable per session,
    follows `/clear` and `--resume`. Claude Code only.
- **Workspaces** — renamed to the basename of the panes' live working
  directory (`foreground_cwd`), decided by majority vote across panes with the
  focused pane breaking ties. Works great with git worktrees
  (`repo`, `repo-alt1`, …).
- **Manual renames win — within a session** — rename an agent yourself and
  the plugin leaves it alone for the rest of that session; when the pane
  moves to a new session, the name follows the session again. Manually
  renamed workspaces are never touched again.

## Install

```bash
herdr plugin install kakigakki/herdr-auto-namer
```

Requirements: herdr ≥ 0.7.0, `python3` on `PATH`, macOS or Linux.
Agent naming currently supports **Claude Code**; workspace naming is
agent-agnostic.

## How agents are matched to sessions

The plugin prefers the session id/path that Claude Code reports through
herdr's official agent integration. For precise matching, install it once:

```bash
herdr integration install claude
```

Without the integration it falls back to mtime correlation — the session
transcript written moments before the idle transition belongs to that pane.
This is right in practice unless several agents in the *same directory*
finish in the same instant; ambiguous rounds are skipped and retried on the
next turn.

## Configuration

Optional. Create `config.json` in the plugin's config dir
(`herdr plugin config-dir auto-namer`):

```json
{
  "rename_agents": true,
  "rename_workspaces": true,
  "agent_naming": "llm",
  "llm_max_len": 12,
  "llm_interval": 180,
  "max_len": 40,
  "mtime_window": 20
}
```

| Key | Default | Meaning |
| --- | --- | --- |
| `rename_agents` | `true` | Auto-name agents |
| `rename_workspaces` | `true` | Sync workspace labels to working directories |
| `agent_naming` | `"llm"` | `"llm"` (haiku summary) or `"session"` (Claude session title) |
| `llm_max_len` | `12` | Max title length in llm mode |
| `llm_interval` | `180` | Min seconds between renames per pane in llm mode |
| `max_len` | `40` | Max name length in session mode |
| `mtime_window` | `20` | Seconds for the session fallback correlation (session mode) |

## Notes

- Everything runs locally; nothing is sent anywhere.
- State (what the plugin named things) lives in the plugin config dir;
  delete it to let the plugin re-adopt manually-renamed items.

## License

MIT
