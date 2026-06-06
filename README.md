# HAM-TDD: Hermes & Antigravity Multi-Agent Test-Driven Development Framework

HAM-TDD is a task-agnostic, multi-agent collaboration framework that enables **Antigravity** (Google DeepMind's coding assistant) and **Hermes** (Nous Research's system-access agent) to collaboratively implement and verify software using Test-Driven Development (TDD).

Instead of target-specific code, this framework provides a general-purpose orchestration harness (`harness.py`) that drives Hermes to complete **any** user-defined task, executing verification checks in a loop until the tests pass.

---

## How It Works: The TDD Feedback Loop

```mermaid
sequenceDiagram
    participant A as Antigravity (Coordinating Reviewer)
    participant H as Hermes (Worker Agent)
    participant V as Verification Runner (Pytest/Script/Linter)
    
    A->>H: Round 1: Present goal & request implementation plan
    Note over H: Hermes plans and writes initial code
    H-->>A: Returns code structure / files written
    
    loop Evaluation
        A->>V: Execute verify command (e.g. pytest tests/)
        V-->>A: Return status + stdout/stderr
        alt Verification Passed
            A->>H: Sign-off: "Verification passed! Task complete."
            Note over A,H: Termination: Loop Exits
        else Verification Failed
            A->>H: Round N: Feed error stack trace & request fixes
            Note over H: Hermes patches code and files
            H-->>A: Returns fix report
        end
    end
```

---

## Features

* **Task-Agnostic Execution:** Works for any language or script—simply specify a goal and a shell verification command (e.g. unit tests, linters, compilation steps).
* **Automatic Error Feedback:** If the verification command fails, the harness automatically captures the exact terminal error output and feeds it directly back to Hermes' session for automated patching.
* **Hermes Session Tracking:** Automatically strips ANSI colors and parses stdout/stderr to track and resume Hermes CLI sessions across execution rounds.
* **Process Env Safety:** Bypasses Windows-specific shell crashes by forcing standard `ComSpec` (`cmd.exe`) variables in child processes.
* **Persistent Logs:** Every agent-to-agent transcript and verification result is logged under `collab_logs/collaboration_transcript.log`.

---

## Setup & Environment

Ensure you have your environment variables set (`GEMINI_API_KEY` or `GOOGLE_API_KEY` for Google Gemini models) and your npm execution shell settings configured correctly as described in [install-hermes-desktop](file:///C:/Users/admin/AppData/Local/hermes/skills/devops/install-hermes-desktop/SKILL.md).

---

## How to Run

Launch the harness by specifying a task and an optional verification command:

```bash
python harness.py --task "Implement a Python function in fib.py that computes Fibonacci numbers, and add unit tests" --verify "pytest fib.py"
```

### CLI Arguments
* `--task`: **(Required)** The description of the goal you want the agents to achieve.
* `--verify`: Optional shell command to run to verify task completion (e.g., `pytest`, `npm test`, `python test.py`).
* `--workspace`: Directory where commands and files are written (default: `C:\Users\admin`).
* `--hermes`: Path to the `hermes.exe` CLI binary.
* `--rounds`: Maximum conversation iterations to try before giving up (default: `5`).
