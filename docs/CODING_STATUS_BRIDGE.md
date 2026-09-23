# Coding-agent status bridge

Keyboard-Agent can optionally turn Vega into a small coding companion. Codex
lifecycle hooks publish a coarse state, and the resident Windows agent renders
that state on the keyboard screen. Normal pet interactions continue to work
when the bridge is not configured.

The bridge has been verified with both of these paths:

1. a Codex CLI running on the same Windows PC as `win_agent.py`;
2. a Codex session running on another machine and relaying its status over SCP.

Claude Code can target the same state protocol through command hooks; the
[Claude Code mapping](#claude-code-hook-mapping-validation-pending) below is
documented for integration, but its end-to-end validation is still pending.
See the [README previews](../README.md#your-coding-companion-codex--claude-code)
for the working, waiting, and completion scenes.

The bridge never transfers prompts, responses, tool arguments, file names, or
logs. It accepts only a fixed lifecycle enum.

## State protocol

| State | Default lifetime | Meaning |
|---|---:|---|
| `working` | 15 minutes | the coding agent is actively handling a turn |
| `waiting` | 30 minutes | the agent needs a decision or approval |
| `completed` | 30 seconds | the turn stopped normally |
| `blocked` | 5 minutes | the turn was interrupted or cannot continue |
| `idle` | immediate | clear this source and restore another active source or the pet scene |

Each JSON payload has this shape:

```json
{
  "version": 1,
  "state": "working",
  "revision": 1,
  "updated_at": 1700000000.0,
  "expires_at": 1700000900.0
}
```

`revision` increases independently for each source. Non-idle events always
expire, so a crashed hook cannot leave the screen in a permanent working state.
Malformed, expired, or replayed payloads are ignored.

## Architecture

```text
Windows Codex hooks ──────────────> data/coding_status.json ───────┐
                                                                  ├─> win_agent.py
Remote Codex hooks -> local spool -> SCP ->                        │      -> Vega
                          data/coding_status_remote.json ──────────┘
```

The two Windows handoff files are read independently. The most recently changed
active source owns the screen. When it expires or emits `idle`, the coordinator
falls back to the other active source, if any. Source priority uses the order
in which Windows observes state changes, not cross-source revision numbers or
sender timestamps. Expiry still uses Unix timestamps, so keep both machines'
clocks synchronized. Sources are local/remote, not separate queues for each
coding conversation; concurrent sessions sharing one inbox can replace each
other's state.

## Windows-local Codex

The local hook writes directly to the repository's ignored `data/` directory.
Use an absolute path in the hook definition because Codex may start in a
different working directory.

The underlying command for a working event is:

```powershell
py -3 C:\absolute\path\to\vega-keyboard-pet\scripts\codex_status_hook.py `
  --state working `
  --state-file C:\absolute\path\to\vega-keyboard-pet\data\coding_status.json
```

Configure the following lifecycle mapping in the user-level Codex hook file:

| Codex event | State | Execution |
|---|---|---|
| `UserPromptSubmit` | `working` | asynchronous |
| `PreToolUse` | `working` | asynchronous heartbeat |
| `PermissionRequest` | `waiting` | asynchronous |
| `Stop` | `completed` | synchronous, with `--hook-response` |
| `Interrupt` | `blocked` | asynchronous |

On Windows, an explicit `cmd.exe` or `.cmd` wrapper is recommended so
environment-variable and quoted-path expansion is deterministic. Every command
should call the same script and state file, changing only `--state`. The `Stop`
command passes `--hook-response` to return JSON. These examples keep it
synchronous to persist the local completion event before the hook returns;
network delivery is still detached. The event and trust requirements are
described in the [official Codex hooks reference](https://learn.chatgpt.com/docs/hooks).

## Claude Code hook mapping (validation pending)

Claude Code has its own command hooks in `~/.claude/settings.json`. Despite its
name, `scripts/codex_status_hook.py` accepts a fixed `--state` argument rather
than a provider-specific stdin payload, so it can be called from either host.
This integration is not yet verified end to end with Claude Code.

| Claude Code event | Emit |
|---|---|
| `UserPromptSubmit` | `working` |
| `PreToolUse` | `working` heartbeat |
| `PermissionRequest` | `waiting` |
| `Stop` | `completed` (response ended, not a correctness verdict) |

For example, this minimal POSIX command-hook configuration covers turn start
and finish. Merge the entries into existing settings, replace the absolute
script path, and add the tool/permission events above if desired. With the
remote relay configured, these commands use its existing spool and inbox.

```json
{
  "hooks": {
    "UserPromptSubmit": [{"hooks": [{
      "type": "command",
      "command": "python3 /absolute/path/to/codex_status_hook.py --state working",
      "timeout": 3
    }]}],
    "Stop": [{"hooks": [{
      "type": "command",
      "command": "python3 /absolute/path/to/codex_status_hook.py --state completed",
      "timeout": 3
    }]}]
  }
}
```

For Windows, use an interpreter and quoting appropriate to the hook shell and
pass `--state-file` for the local inbox, as described above. Do not copy Codex's
`Interrupt` or `commandWindows` fields into Claude settings. Check the
[Claude Code hooks reference](https://code.claude.com/docs/en/hooks) for its
event and shell behavior, then complete the visual verification below.

## Remote Codex relay

The same script can maintain a private local spool and relay it to the dedicated
remote inbox on the Windows PC. Configure passwordless, non-interactive SCP
first. Then save this private configuration outside the repository as
`~/.config/keyboard-agent/status-relay.json`:

```json
{
  "destination": "host-alias:/path/to/keyboard-agent/data/coding_status_remote.json",
  "identity_file": "/path/to/private/key"
}
```

Restrict that file to the local user. Do not place endpoints, account names, or
key paths in repository files. The destination must be
`coding_status_remote.json`, not the local Windows inbox, because each source
owns its own revision sequence.

Create a user-level `~/.codex/hooks.json` on the remote machine. Replace the
script path below with an absolute path:

```json
{
  "description": "Local Keyboard-Agent status display.",
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/codex_status_hook.py --state working",
            "async": true,
            "timeout": 3
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/codex_status_hook.py --state working",
            "async": true,
            "timeout": 3
          }
        ]
      }
    ],
    "PermissionRequest": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/codex_status_hook.py --state waiting",
            "async": true,
            "timeout": 3
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/codex_status_hook.py --state completed --hook-response",
            "timeout": 3
          }
        ]
      }
    ],
    "Interrupt": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/codex_status_hook.py --state blocked",
            "async": true,
            "timeout": 3
          }
        ]
      }
    ]
  }
}
```

The hook updates the local spool atomically and detaches network delivery, so a
slow or unavailable relay cannot delay the coding turn. Repeated `working`
events are deduplicated, with periodic heartbeats extending the expiry. SCP uses
bounded retries and never receives hook stdin.

Optional environment overrides are available for non-default layouts:

- `VEGA_STATUS_STATE_FILE`: emitter spool file;
- `VEGA_STATUS_RELAY_CONFIG`: private relay configuration;
- `VEGA_CODING_STATUS_FILE`: Windows-local inbox;
- `VEGA_REMOTE_CODING_STATUS_FILE`: Windows remote inbox.

## Trust and session lifecycle

Codex requires review for every new or changed non-managed hook definition. Use
`/hooks` to inspect and trust `Local Keyboard-Agent status display.` After
installing, editing, or trusting the hook, start a fresh conversation before
testing. An already-open conversation may keep the hook set it loaded when the
session started. A CLI test does not by itself establish that a separate editor
extension has loaded the same hooks; verify in the actual host you use.

Changing the Python script without changing the hook command does not require
putting secrets into the hook definition. If the command itself changes, review
the new definition again.

## Verification

1. Start or restart `win_agent.py` and confirm exactly one instance is running.
2. Submit a harmless Codex task that uses at least one tool.
3. Confirm Vega shows the working scene during the turn and the completed scene
   when the turn stops.
4. Confirm the relevant inbox changes:

   ```powershell
   Get-Content .\data\coding_status.json
   Get-Content .\data\coding_status_remote.json
   ```

5. Check only the status markers in the bounded runtime log:

   ```powershell
   Get-Content .\agent_run.log -Tail 150 |
     Select-String -SimpleMatch '[coding-status]'
   ```

Expected transitions look like:

```text
[coding-status] working revision=12
[coding-status] completed revision=13
[coding-status] cleared; restored pet scene
```

Full hardware verification is visual: a zero exit code means the serial tool
reported success. Confirm the intended scene on the physical keyboard too.

## Troubleshooting

| Symptom | Check |
|---|---|
| Hook is trusted but nothing changes | Start a fresh conversation; do not use a session that was already open when the hook was installed. |
| Local CLI works but remote Codex does not | Check the private relay configuration, non-interactive SCP, and `coding_status_remote.json`. |
| Inbox changes but no status marker appears | Restart `win_agent.py` after upgrading and confirm only one instance is running. |
| Status marker appears but the screen does not change | Check the following `[push] animation` result and verify the keyboard visually. |
| A lower revision is ignored | Keep one persistent spool per source; do not send independent revision sequences to the same inbox. |
| Working remains after a failed turn | Wait for its expiry or emit `idle`; confirm that `Stop` is synchronous and returns valid JSON. |
| Hook delays Codex | Keep network delivery detached and all non-`Stop` handlers asynchronous. |

## Privacy and repository safety

- The hook never reads stdin and never serializes task content.
- Only the enum, revision, and timestamps cross the relay.
- Status files live under ignored runtime directories.
- Relay destinations, account names, and identity paths belong only in the
  private configuration file.
- Never commit hook trust databases, SSH material, runtime logs, or status JSON.
