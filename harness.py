import subprocess
import argparse
import json
import sys
import os
import re

# Enforce UTF-8 for console output to avoid encoding crashes on Windows
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

DEFAULT_HERMES_PATH = r"C:\Users\admin\AppData\Local\hermes\hermes-agent\venv\Scripts\hermes.exe"
DEFAULT_WORKSPACE = r"C:\Users\admin"

def strip_ansi_codes(text):
    if not text:
        return ""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def extract_session_id(stdout, stderr):
    for stream in (stdout, stderr):
        if not stream:
            continue
        clean_text = strip_ansi_codes(stream)
        match = re.search(r"Session:\s+([0-9a-zA-Z_]+)", clean_text)
        if match:
            return match.group(1)
        match = re.search(r"--resume\s+([0-9a-zA-Z_]+)", clean_text)
        if match:
            return match.group(1)
    return None

def clean_output(text):
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        line_clean = strip_ansi_codes(line).strip()
        if not line_clean:
            continue
        # Strip TUI wrapping characters
        if "⚕ Hermes" in line_clean or "───" in line_clean or "╭─" in line_clean or "╰─" in line_clean:
            continue
        if line_clean.startswith("│") or line_clean.startswith("╭") or line_clean.startswith("╰"):
            line_clean = line_clean.lstrip("│").strip()
        cleaned_lines.append(line_clean)
    return "\n".join(cleaned_lines)

class MultiAgentHarness:
    def __init__(self, task_desc, verify_cmd=None, workspace=DEFAULT_WORKSPACE, hermes_path=DEFAULT_HERMES_PATH, max_rounds=5):
        self.task_desc = task_desc
        self.verify_cmd = verify_cmd
        self.workspace = workspace
        self.hermes_path = hermes_path
        self.max_rounds = max_rounds
        self.session_id = None

        # Clean up common Windows quoting artifacts in verify_cmd
        if self.verify_cmd:
            # If --rounds got absorbed into verify_cmd due to Windows quote escaping
            match = re.search(r'\\?\s+--rounds\s+(\d+)\s*$', self.verify_cmd)
            if match:
                self.max_rounds = int(match.group(1))
                self.verify_cmd = self.verify_cmd[:match.start()]
            
            # If --workspace got absorbed
            match = re.search(r'\\?\s+--workspace\s+(\S+)\s*$', self.verify_cmd)
            if match:
                self.workspace = match.group(1).strip('"\'')
                self.verify_cmd = self.verify_cmd[:match.start()]

            # If --hermes got absorbed
            match = re.search(r'\\?\s+--hermes\s+(\S+)\s*$', self.verify_cmd)
            if match:
                self.hermes_path = match.group(1).strip('"\'')
                self.verify_cmd = self.verify_cmd[:match.start()]

            # Clean trailing backslash if it was an escaped quote artifact
            # e.g., powershell -Command " Get-Content C:\Users\admin\hello.txt\ -> needs a closing quote
            if self.verify_cmd.count('"') % 2 != 0:
                if self.verify_cmd.endswith('\\'):
                    self.verify_cmd = self.verify_cmd[:-1] + '"'
                else:
                    self.verify_cmd = self.verify_cmd + '"'

        self.log_dir = os.path.join(self.workspace, "collab_logs")
        
        # Ensure log directory exists
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file = os.path.join(self.log_dir, "collaboration_transcript.log")

    def log(self, message):
        print(message)
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(message + "\n")

    def update_session_source(self):
        if not self.session_id:
            return
        
        # Path to Hermes state database
        local_appdata = os.environ.get("LOCALAPPDATA", r"C:\Users\admin\AppData\Local")
        db_path = os.path.join(local_appdata, "hermes", "state.db")
        if not os.path.exists(db_path):
            db_path = r"C:\Users\admin\AppData\Local\hermes\state.db"
            
        if not os.path.exists(db_path):
            return
            
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            cursor = conn.execute("UPDATE sessions SET source = 'tui' WHERE id = ?", (self.session_id,))
            conn.commit()
            if cursor.rowcount > 0:
                self.log(f"[Harness]: Surface update - Set session source to 'tui' in state.db")
            conn.close()
        except Exception as e:
            self.log(f"[Harness Warning]: Failed to update session source in state.db: {e}")

    def run_hermes_turn(self, query):
        cmd = [self.hermes_path, "chat", "-q", query]
        if self.session_id:
            cmd.extend(["--resume", self.session_id])
            
        # Ensure correct ComSpec is passed to prevent Windows process crashes
        env = os.environ.copy()
        env["ComSpec"] = r"C:\Windows\System32\cmd.exe"
        
        # Tag the session as 'tui' so it surfaces in the Hermes Desktop App history sidebar
        env["HERMES_SESSION_SOURCE"] = "tui"
        
        self.log(f"\n--- Spawning Hermes Subprocess (Session: {self.session_id or 'New'}) ---")
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=self.workspace, env=env)
        
        return result.stdout, result.stderr

    def run_verification(self):
        if not self.verify_cmd:
            return True, "No verification command configured."
        
        self.log(f"\n--- Running Verification Command: {self.verify_cmd} ---")
        # Run in standard shell environment
        result = subprocess.run(self.verify_cmd, shell=True, capture_output=True, text=True, cwd=self.workspace)
        
        output = (result.stdout + "\n" + result.stderr).strip()
        passed = (result.returncode == 0)
        return passed, output

    def execute_collaboration(self):
        self.log("=========================================================")
        self.log("      HERMES-ANTIGRAVITY MULTI-AGENT COLLABORATION")
        self.log("=========================================================")
        self.log(f"Workspace: {self.workspace}")
        self.log(f"Task Goal: {self.task_desc}")
        if self.verify_cmd:
            self.log(f"Verification: {self.verify_cmd}")
        self.log("=========================================================")

        # Round 1: Initiate task with Hermes
        current_prompt = (
            f"Hello Hermes! I am Antigravity, your coordinating partner agent. "
            f"We have been assigned the following task:\n\n\"{self.task_desc}\"\n\n"
            f"Please propose an implementation plan or draft the initial code files to complete this goal."
        )
        
        for round_idx in range(1, self.max_rounds + 1):
            self.log(f"\n[Round {round_idx}/{self.max_rounds}]")
            self.log(f"[Antigravity $\\rightarrow$ Hermes]:\n{current_prompt}")
            
            stdout, stderr = self.run_hermes_turn(current_prompt)
            
            # Extract Session ID if not already set
            if not self.session_id:
                self.session_id = extract_session_id(stdout, stderr)
                if self.session_id:
                    self.log(f"[Harness]: Captured Session ID: {self.session_id}")
                    self.update_session_source()
            
            cleaned_reply = clean_output(stdout)
            self.log(f"\n[Hermes]:\n{cleaned_reply}")
            
            if not cleaned_reply:
                self.log("\n[Harness ERROR]: Received empty reply from Hermes. Exiting loop.")
                break
                
            # Run local verification
            passed, verify_output = self.run_verification()
            if passed:
                self.log(f"\n[Verification SUCCESS]:\n{verify_output}")
                self.log("\n[Antigravity]: Verification passed successfully! The task is fully complete. Great collaborating with you!")
                
                # Signal task completion to Hermes session
                self.run_hermes_turn("Verification passed successfully! Task is complete. Excellent work.")
                break
            else:
                self.log(f"\n[Verification FAILURE]:\n{verify_output}")
                
                # Feed error output back to Hermes for the next round
                current_prompt = (
                    f"The implementation failed verification with the following output:\n\n"
                    f"```\n{verify_output}\n```\n\n"
                    f"Please analyze the errors, modify the code files, and verify the patch in your session."
                )
                
        self.update_session_source()
        self.log("\n=========================================================")
        self.log("Collaboration session finished.")
        self.log(f"Transcript logged to: {self.log_file}")
        self.log("=========================================================")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Task-Agnostic Multi-Agent Collaboration Harness")
    parser.add_argument("--task", type=str, required=True, help="Description of the goal to achieve")
    parser.add_argument("--verify", type=str, default=None, help="Optional shell command to run to verify task completion")
    parser.add_argument("--workspace", type=str, default=DEFAULT_WORKSPACE, help="Workspace directory for execution")
    parser.add_argument("--hermes", type=str, default=DEFAULT_HERMES_PATH, help="Path to hermes.exe CLI")
    parser.add_argument("--rounds", type=int, default=5, help="Maximum conversation rounds")
    
    args = parser.parse_args()
    
    harness = MultiAgentHarness(
        task_desc=args.task,
        verify_cmd=args.verify,
        workspace=args.workspace,
        hermes_path=args.hermes,
        max_rounds=args.rounds
    )
    harness.execute_collaboration()
