# HAM-TDD

HAM-TDD (Hermes and Antigravity Multi-Agent Test-Driven Development) is a Python harness that sends a task to the Hermes CLI, runs a shell command you supply, and feeds that command's output back to Hermes until the command exits 0 or the round limit is hit.

`harness.py` is the program. It does not implement a product feature by itself. You provide the goal and the check. `HAM_TDD_SPEC.md` and the files under `skills/` describe the MCP message flow and the skill text meant for Hermes.

## Prerequisites

- Python 3.7 or newer. `harness.py` imports only the standard library. This repository has no `requirements.txt`, `pyproject.toml`, or other package manifest.
- A Hermes CLI executable. The harness launches `<hermes> mcp serve`. When that server has no conversation and no channel, the harness runs `<hermes> chat -q` instead, and later adds `--resume <session_id>` when it can parse a session id from the CLI output.
- A writable workspace. Each run appends `<workspace>/collab_logs/collaboration_transcript.log`.

When `LOCALAPPDATA` is set and this file exists, the default `--hermes` path is `%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\hermes.exe`. When `USERPROFILE` is set and that directory exists, it is the default `--workspace`. Otherwise the script uses built-in Windows fallback paths. Pass `--hermes` and `--workspace` on any machine where those defaults are missing.

Child processes get `ComSpec` set to `C:\Windows\System32\cmd.exe`. CLI fallback mode also sets `HERMES_SESSION_SOURCE` to `tui`. If `%LOCALAPPDATA%\hermes\state.db` exists, the harness sets that session's `source` column to `tui`.

## Install, build, run, and test

Cloning the repository is the install. There is no build script and no test suite.

From the repository root, these commands check the script and print the CLI:

```bash
python3 -m py_compile harness.py
python3 harness.py --help
```

On Windows the interpreter is often named `python`. The same two commands work with that name when `python3` is absent.

A full run needs Hermes on the machine. This invocation matches the arguments in `harness.py`:

```bash
python3 harness.py \
  --task "Describe the goal in one sentence" \
  --verify "python3 -m py_compile harness.py" \
  --workspace "." \
  --hermes "hermes" \
  --rounds 5
```

`--hermes` must be the Hermes executable, or the name `hermes` when that executable is on `PATH`. Replace `--task` with the goal. Replace `--verify` with the check that should pass when the goal is done. The harness runs that string through the system shell with `--workspace` as the working directory. Exit code 0 means the check passed. Omitting `--verify` makes the harness treat the check as passed and stop after the first Hermes reply.

## Usage

```text
python3 harness.py --task TASK [--verify VERIFY] [--workspace WORKSPACE] [--hermes HERMES] [--rounds ROUNDS] [--target TARGET]
```

| Flag | Required | Default | Role |
| --- | --- | --- | --- |
| `--task` | yes | | Goal text sent to Hermes |
| `--verify` | no | none | Shell command whose exit code decides success |
| `--workspace` | no | `USERPROFILE` when that directory exists, otherwise the script fallback | Working directory for CLI mode, the check, and the log |
| `--hermes` | no | `hermes.exe` under the local Hermes install when that file exists, otherwise the script fallback | Path to the Hermes executable |
| `--rounds` | no | `5` | Maximum task rounds |
| `--target` | no | first conversation from `conversations_list`, otherwise the first entry from `channels_list` | MCP session key, shaped like `platform:chat` |

One run does the following:

1. Writes the transcript under `<workspace>/collab_logs/collaboration_transcript.log`.
2. Starts the Hermes MCP server and sends the task with `messages_send`.
3. Waits on `events_wait` (30 second polls, 300 second overall cap) for an assistant message. An `approval_requested` event is answered with `permissions_respond` and decision `allow-once`.
4. Runs `--verify` when it is set. Exit code 0 sends a short completion message and stops the loop. Any other exit code sends the combined stdout and stderr into the next round.
5. Drops to `hermes chat -q` when MCP returns no conversation and no channel.

An empty Hermes reply ends the loop early. If a shell pastes `--rounds`, `--workspace`, or `--hermes` onto the end of `--verify`, the harness removes those flags from the check string before running it.

`HAM_TDD_SPEC.md` documents Hermes MCP tools and a lead session that can call `delegate_task` for research, coding, and QA subagents. That split is guidance for Hermes. `harness.py` talks to one Hermes session and runs the verification command locally.

## Layout

```text
harness.py
HAM_TDD_SPEC.md
README.md
skills/ham-tdd/SKILL.md
skills/multi-agent-coordination/SKILL.md
skills/multi-agent-coordination/references/ham-tdd-mcp-payloads.md
```

`.gitignore` ignores `collab_logs/`, virtualenvs, bytecode, and local env files. The log directory is created when the harness runs.

## License

`skills/ham-tdd/SKILL.md` and `skills/multi-agent-coordination/SKILL.md` set `license: MIT` in their frontmatter. This repository does not contain a `LICENSE` file.
