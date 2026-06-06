import subprocess
import re
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

HERMES_PATH = r"C:\Users\admin\AppData\Local\hermes\hermes-agent\venv\Scripts\hermes.exe"
WORKSPACE_DIR = r"C:\Users\admin"

def run_hermes(query, session_id=None):
    cmd = [HERMES_PATH, "chat", "-q", query]
    if session_id:
        cmd.extend(["--resume", session_id])
    
    # Ensure correct ComSpec is used in the subprocess env
    env = os.environ.copy()
    env["ComSpec"] = r"C:\Windows\System32\cmd.exe"
    
    print(f"\n--- Running Command: {' '.join(cmd)} ---")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=WORKSPACE_DIR, env=env)
    
    return result.stdout, result.stderr

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
    # Remove boxes and UI wrappers printed by the TUI/CLI
    lines = text.split("\n")
    cleaned_lines = []
    in_box = False
    for line in lines:
        line_clean = strip_ansi_codes(line).strip()
        if not line_clean:
            continue
        # Skip box borders
        if "⚕ Hermes" in line_clean or "───" in line_clean or "╭─" in line_clean or "╰─" in line_clean:
            continue
        if line_clean.startswith("│") or line_clean.startswith("╭") or line_clean.startswith("╰"):
            line_clean = line_clean.lstrip("│").strip()
        cleaned_lines.append(line_clean)
    return "\n".join(cleaned_lines)

def main():
    print("====================================================")
    # Turn 1: Antigravity initiates the request
    prompt_1 = (
        "Hello Hermes! I am Antigravity, a Gemini-powered coding assistant. "
        "Let us collaborate on writing a lightweight Python script that generates a premium, "
        "dark-mode HTML system status dashboard showing CPU, RAM, Disk space, and the active Windows Page File configuration. "
        "What is your proposed HTML structure and design style for this dashboard?"
    )
    
    print(f"\n[Antigravity]: {prompt_1}")
    stdout, stderr = run_hermes(prompt_1)
    
    session_id = extract_session_id(stdout, stderr)
    cleaned_stdout = clean_output(stdout)
    print(f"\n[Hermes (Session: {session_id})]:\n{cleaned_stdout}")
    
    if not session_id:
        print("Error: Could not extract Session ID from Hermes output.")
        sys.exit(1)
        
    # Turn 2: Antigravity guides Hermes to implement the stats collection functions
    prompt_2 = (
        "Excellent design proposal! Let's implement the Python code to collect these stats on Windows. "
        "We should query CPU (via psutil or wmi), RAM (using CimInstance or psutil), and read the active pagefile settings from the registry or CIM. "
        "Please write the Python function get_system_stats() and integrate it with your HTML template."
    )
    
    print(f"\n[Antigravity]: {prompt_2}")
    stdout2, stderr2 = run_hermes(prompt_2, session_id)
    cleaned_stdout2 = clean_output(stdout2)
    print(f"\n[Hermes]:\n{cleaned_stdout2}")
    
    # Turn 3: Antigravity instructs Hermes to write the script to a file
    prompt_3 = (
        "The code looks fantastic and highly optimized. Let's write the complete code into a file "
        "C:\\\\Users\\\\admin\\\\AppData\\\\Local\\\\hermes\\\\hermes-agent\\\\system_dashboard.py and run it to verify it works."
    )
    
    print(f"\n[Antigravity]: {prompt_3}")
    stdout3, stderr3 = run_hermes(prompt_3, session_id)
    cleaned_stdout3 = clean_output(stdout3)
    print(f"\n[Hermes]:\n{cleaned_stdout3}")
    
    print("\n====================================================")
    print("Conversation loop complete!")

if __name__ == "__main__":
    main()
