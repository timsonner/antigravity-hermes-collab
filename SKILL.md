---
name: ham-tdd
description: "Orchestrate task-agnostic, multi-agent Test-Driven Development (TDD) loops between Antigravity and Hermes."
version: 1.0.0
author: Antigravity & Hermes
license: MIT
platforms: [windows, macos, linux]
metadata:
  hermes:
    tags: [tdd, multi-agent, collaboration, orchestrator, testing]
    related_skills: [hermes-agent, install-hermes-desktop]
---

# HAM-TDD: Multi-Agent TDD Collaboration Skill

Use this skill to orchestrate or participate in a collaborative Test-Driven Development (TDD) loop between **Antigravity** (Google DeepMind's orchestrating assistant) and **Hermes** (Nous Research's system-execution agent). It enables task-agnostic execution, automated error feedback, and continuous verification loops until a target task passes.

---

## 1. Skill Capabilities

This skill wraps the orchestration logic in `harness.py` to allow:
* **Dynamic Agent-to-Agent Handshakes:** Initiates, resumes, and keeps track of Hermes execution sessions (`--resume <session_id>`).
* **Continuous Test & Repair Loops:** Evaluates implementations against a user-specified command (e.g. unit tests, build commands, checkers) and feeds failing outputs back to the worker session.
* **Platform-Agnostic Parsing:** Strips TUI framing characters, ANSI formatting, and parses exit codes to accurately assess success/failure.
* **Windows CMD/PowerShell Safety:** Automatically repairs quoting artifacts, escaped characters, and trailing backslashes when command-line parameters get absorbed during multi-layered shell spawns.

---

## 2. Command Line API

Run the harness directly from the command line in the repository workspace:

```bash
python harness.py --task "<task_description>" --verify "<verification_command>" [options]
```

### Parameters
* `--task`: **(Required)** Text description detailing the exact task, feature, or file(s) Hermes needs to create or modify.
* `--verify`: Optional shell command run by the harness to verify execution status (e.g. `pytest tests/`, `npm run build`, `python verify.py`).
* `--workspace`: Target workspace directory for execution (defaults to parent directory `C:\Users\admin`).
* `--hermes`: Path to the `hermes.exe` CLI binary.
* `--rounds`: Maximum feedback iterations (default: `5`).

---

## 3. How the Agents Interact

1. **Kickoff:** Antigravity (via the harness) initiates the session by passing the task instructions to Hermes.
2. **Implementation:** Hermes proposes files or patches them directly in the workspace.
3. **Verification:** The harness executes the test script. 
   * **If success (exit code 0):** The harness reports success to Hermes, logs the session, and exits.
   * **If failure (exit code non-zero):** The harness captures the exact terminal error traceback, feeds it back to Hermes as the next round's query, and prompts for code repair.

---

## 4. Best Practices & Windows Tips

* **Quoting Arguments:** When passing complex nested strings in Command Prompt or PowerShell, double quotes may be absorbed. The harness has built-in regex filters to strip absorbed trailing `--rounds`, `--workspace`, or `--hermes` arguments from the verification block.
* **ComSpec Overrides:** Because Windows child processes can inherit shell environments differently, the harness explicitly overrides the child process environment `ComSpec` variable to target `cmd.exe` directly when spawning Hermes CLI instances to avoid path resolution errors.
* **Persistent Logs:** Complete round histories and verification output logs are saved in `collab_logs/collaboration_transcript.log` for inspection.

---

## 5. Hierarchical Corporate Delegation Pattern

To solve complex engineering objectives, agents can delegate sub-tasks within a hierarchical "corporate structure" to isolate context and scale capability:

1. **Executive Board (Antigravity Orchestrator):** Manages high-level requirements and serves as the quality gatekeeper (runs tests).
2. **Project Manager (Lead Hermes):** Coordinates the repository workspace, runs build steps, and allocates specialized worker subagents for sub-tasks.
3. **Specialized Worker Subagents:**
   * **Research Subagent:** Handles documentation lookups and web searches (keeps lead developer's context clean).
   * **Feature Coder Subagent:** Implements target features and modules.
   * **QA Subagent:** Writes test harnesses and targets edge cases to break and strengthen the software.

*Recommended Skill Prompting:* When giving tasks to Hermes, explicitly instruct the agent: 
> "Evaluate if this task requires documentation research or unit testing. If so, spawn specialized subagents to implement or research, and integrate their outputs back in your primary session."
