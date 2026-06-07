import subprocess
import argparse
import json
import sys
import os
import re
import threading
import queue
import time

class SimpleMCPClient:
    def __init__(self, command, args=[]):
        env = os.environ.copy()
        env["ComSpec"] = r"C:\Windows\System32\cmd.exe"
        
        self.proc = subprocess.Popen(
            [command] + args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            encoding='utf-8',
            env=env
        )
        self.id_counter = 1
        self.waiters = {}
        self.lock = threading.Lock()
        
        # Start background reader thread
        self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.reader_thread.start()
        
        # Start background log forwarder thread
        self.log_thread = threading.Thread(target=self._log_forwarder, daemon=True)
        self.log_thread.start()

    def _reader_loop(self):
        while True:
            line = self.proc.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line)
                msg_id = msg.get("id")
                if msg_id is not None:
                    with self.lock:
                        q = self.waiters.get(msg_id)
                    if q:
                        q.put(msg)
            except Exception:
                pass

    def _log_forwarder(self):
        while True:
            line = self.proc.stderr.readline()
            if not line:
                break
            sys.stderr.write(f"[MCP Server Log]: {line}")

    def call_tool(self, tool_name, arguments={}):
        res = self.send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })
        if isinstance(res, dict) and "content" in res:
            content_list = res.get("content", [])
            if content_list and isinstance(content_list, list):
                first_block = content_list[0]
                if isinstance(first_block, dict) and first_block.get("type") == "text":
                    return first_block.get("text", "")
        return res

    def send_request(self, method, params={}):
        req_id = self.id_counter
        self.id_counter += 1
        
        q = queue.Queue()
        with self.lock:
            self.waiters[req_id] = q
            
        req = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": req_id
        }
        
        try:
            self.proc.stdin.write(json.dumps(req) + "\n")
            self.proc.stdin.flush()
        except Exception as e:
            with self.lock:
                self.waiters.pop(req_id, None)
            raise e
            
        resp = q.get()
        with self.lock:
            self.waiters.pop(req_id, None)
            
        if "error" in resp:
            raise RuntimeError(f"MCP Error: {resp['error']}")
        return resp.get("result")

    def initialize(self):
        init_res = self.send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "SimpleMCPClient",
                "version": "1.0.0"
            }
        })
        
        req = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
        self.proc.stdin.write(json.dumps(req) + "\n")
        self.proc.stdin.flush()

    def close(self):
        try:
            self.proc.terminate()
            self.proc.wait(timeout=2)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass

# Enforce UTF-8 for console output to avoid encoding crashes on Windows
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

_local_appdata = os.environ.get("LOCALAPPDATA", r"C:\Users\admin\AppData\Local")
_user_profile = os.environ.get("USERPROFILE", r"C:\Users\admin")

DEFAULT_HERMES_PATH = os.path.join(_local_appdata, "hermes", "hermes-agent", "venv", "Scripts", "hermes.exe")
if not os.path.exists(DEFAULT_HERMES_PATH):
    DEFAULT_HERMES_PATH = r"C:\Users\admin\AppData\Local\hermes\hermes-agent\venv\Scripts\hermes.exe"

DEFAULT_WORKSPACE = _user_profile
if not os.path.exists(DEFAULT_WORKSPACE):
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
    def __init__(self, task_desc, verify_cmd=None, workspace=DEFAULT_WORKSPACE, hermes_path=DEFAULT_HERMES_PATH, max_rounds=5, target=None):
        self.task_desc = task_desc
        self.verify_cmd = verify_cmd
        self.workspace = workspace
        self.hermes_path = hermes_path
        self.max_rounds = max_rounds
        self.session_id = None
        self.target = target
        self.mcp_client = None
        self.last_event_cursor = 0
        self.use_cli_fallback = False

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

    def run_hermes_turn_mcp(self, query):
        """Runs a turn using the stdio MCP server."""
        if self.use_cli_fallback:
            stdout, stderr = self.run_hermes_turn(query)
            if not self.session_id:
                self.session_id = extract_session_id(stdout, stderr)
                if self.session_id:
                    self.log(f"[Harness]: Captured Session ID: {self.session_id}")
                    self.update_session_source()
            return stdout, stderr

        if not self.mcp_client:
            self.log(f"[Harness]: Starting Hermes MCP server: {self.hermes_path} mcp serve")
            self.mcp_client = SimpleMCPClient(self.hermes_path, ["mcp", "serve"])
            self.mcp_client.initialize()
            self.log("[Harness]: MCP client initialized successfully.")
            
            # Resolve target and initial session_key / session_id
            if not self.target:
                try:
                    res_str = self.mcp_client.call_tool("conversations_list", {"limit": 5})
                    res = json.loads(res_str)
                    conversations = res.get("conversations", [])
                    if conversations:
                        self.target = conversations[0].get("session_key")
                        self.session_id = conversations[0].get("session_id")
                        self.log(f"[Harness]: Defaulting target to most recent conversation: {self.target} (Session ID: {self.session_id})")
                    else:
                        # Try to resolve target via channels_list
                        self.log("[Harness]: No active conversations found. Querying available channels...")
                        chan_str = self.mcp_client.call_tool("channels_list")
                        chan_res = json.loads(chan_str)
                        channels = chan_res.get("channels", [])
                        if channels:
                            self.target = channels[0].get("target")
                            self.log(f"[Harness]: Defaulting target to first available channel: {self.target}")
                        else:
                            self.log("[Harness Warning]: No active conversations or channels found. Falling back to local CLI mode...")
                            self.use_cli_fallback = True
                except Exception as e:
                    self.log(f"[Harness Warning]: No active conversations or channels found. Falling back to local CLI mode...")
                    self.use_cli_fallback = True
                    
            if self.use_cli_fallback:
                if self.mcp_client:
                    self.mcp_client.close()
                    self.mcp_client = None
                stdout, stderr = self.run_hermes_turn(query)
                if not self.session_id:
                    self.session_id = extract_session_id(stdout, stderr)
                    if self.session_id:
                        self.log(f"[Harness]: Captured Session ID: {self.session_id}")
                        self.update_session_source()
                return stdout, stderr
            else:
                try:
                    res_str = self.mcp_client.call_tool("conversations_list", {"limit": 100})
                    res = json.loads(res_str)
                    conversations = res.get("conversations", [])
                    for conv in conversations:
                        if conv.get("session_key") == self.target:
                            self.session_id = conv.get("session_id")
                            self.log(f"[Harness]: Found existing session for target {self.target}: {self.session_id}")
                            break
                except Exception as e:
                    self.log(f"[Harness Warning]: Failed to search conversations for target {self.target}: {e}")

        # Send the query using messages_send
        self.log(f"[Harness MCP]: Sending message to target {self.target}...")
        send_res_str = self.mcp_client.call_tool("messages_send", {
            "target": self.target,
            "message": query
        })
        self.log(f"[Harness MCP messages_send response]: {send_res_str}")
        
        # Now wait for the assistant's reply using events_wait
        self.log("[Harness MCP]: Waiting for assistant response events...")
        reply = None
        start_time = time.time()
        timeout = 300
        
        while time.time() - start_time < timeout:
            try:
                wait_res_str = self.mcp_client.call_tool("events_wait", {
                    "after_cursor": self.last_event_cursor,
                    "session_key": self.target,
                    "timeout_ms": 30000
                })
                
                wait_res = json.loads(wait_res_str)
                event = wait_res.get("event")
                if not event:
                    continue
                
                event_cursor = event.get("cursor")
                if event_cursor:
                    self.last_event_cursor = max(self.last_event_cursor, event_cursor)
                
                event_type = event.get("type")
                if event_type == "message":
                    role = event.get("role")
                    content = event.get("content")
                    self.log(f"[Harness MCP event]: Message from {role} (cursor {event_cursor}): {content[:100]}...")
                    
                    if role == "assistant":
                        self.log("[Harness MCP]: Assistant reply detected. Reading full conversation history...")
                        try:
                            history_str = self.mcp_client.call_tool("messages_read", {
                                "session_key": self.target,
                                "limit": 5
                            })
                            history = json.loads(history_str)
                            messages = history.get("messages", [])
                            for msg in reversed(messages):
                                if msg.get("role") == "assistant":
                                    reply = msg.get("content")
                                    if not self.session_id:
                                        self.session_id = history.get("session_id")
                                    break
                        except Exception as e:
                            self.log(f"[Harness Warning]: Failed to read message history: {e}. Falling back to event content.")
                            reply = content
                        
                        if reply:
                            break
                elif event_type == "approval_requested":
                    self.log(f"[Harness MCP event]: Approval requested: {event.get('data')}")
                    approval_id = event.get("approval_id") or event.get("data", {}).get("approval_id")
                    if approval_id:
                        self.log(f"[Harness MCP]: Auto-approving request {approval_id}...")
                        try:
                            resp = self.mcp_client.call_tool("permissions_respond", {
                                "id": approval_id,
                                "decision": "allow-once"
                            })
                            self.log(f"[Harness MCP permissions_respond response]: {resp}")
                        except Exception as e:
                            self.log(f"[Harness Warning]: Failed to approve request: {e}")
                    else:
                        try:
                            list_res_str = self.mcp_client.call_tool("permissions_list_open")
                            list_res = json.loads(list_res_str)
                            requests = list_res.get("requests", [])
                            for req in requests:
                                req_id = req.get("id") or req.get("approval_id")
                                if req_id:
                                    self.log(f"[Harness MCP]: Auto-approving pending request {req_id} from list...")
                                    self.mcp_client.call_tool("permissions_respond", {
                                        "id": req_id,
                                        "decision": "allow-once"
                                    })
                        except Exception as e:
                            self.log(f"[Harness Warning]: Failed to auto-approve list: {e}")
                elif event_type == "approval_resolved":
                    self.log(f"[Harness MCP event]: Approval resolved: {event.get('data')}")
                else:
                    self.log(f"[Harness MCP event]: Received event of type {event_type}")
                    
            except Exception as e:
                self.log(f"[Harness Warning]: Error waiting for events: {e}")
                time.sleep(1)
        
        if not reply:
            self.log("[Harness MCP ERROR]: Timed out waiting for Hermes assistant reply.")
            return "", "Timeout"
            
        return reply, ""

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
            
            stdout, stderr = self.run_hermes_turn_mcp(current_prompt)
            
            if self.session_id:
                self.update_session_source()
            
            # When using CLI fallback mode, stdout contains raw terminal/TUI output and needs cleaning.
            # Otherwise, stdout contains clean markdown directly from the MCP session database.
            if self.use_cli_fallback:
                cleaned_reply = clean_output(stdout)
            else:
                cleaned_reply = stdout
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
                self.run_hermes_turn_mcp("Verification passed successfully! Task is complete. Excellent work.")
                break
            else:
                self.log(f"\n[Verification FAILURE]:\n{verify_output}")
                
                # Feed error output back to Hermes for the next round
                current_prompt = (
                    f"The implementation failed verification with the following output:\n\n"
                    f"```\n{verify_output}\n```\n\n"
                    f"Please analyze the errors, modify the code files, and verify the patch in your session."
                )
            
            # Refresh the session UI after the turn is recorded and verification is complete
            self.update_session_source()
                
        self.update_session_source()
        if self.mcp_client:
            self.mcp_client.close()
            self.mcp_client = None
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
    parser.add_argument("--target", type=str, default=None, help="MCP delivery target (e.g. telegram:6308981865)")
    
    args = parser.parse_args()
        
    harness = MultiAgentHarness(
        task_desc=args.task,
        verify_cmd=args.verify,
        workspace=args.workspace,
        hermes_path=args.hermes,
        max_rounds=args.rounds,
        target=args.target
    )
    harness.execute_collaboration()
