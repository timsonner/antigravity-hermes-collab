# Reference: HAM-TDD Multi-Agent MCP Payloads & Integration Specs

This reference document contains the exact JSON-RPC request/response payload examples, Windows portability tricks, and bug-avoidance configurations gathered during the development of the **HAM-TDD** (Hermes & Antigravity Multi-Agent Test-Driven Development) harness.

---

## 1. JSON-RPC Protocol Payloads

When communicating with the Hermes MCP server (`hermes mcp serve`) over stdio, the client launches the process and interacts via standard JSON-RPC 2.0.

### Client Initialization
The client must send an `initialize` request before executing tools, followed by a non-id `notifications/initialized` notification.

**Request:**
```json
{
  "jsonrpc": "2.0",
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {
      "name": "SimpleMCPClient",
      "version": "1.0.0"
    }
  },
  "id": 1
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2024-11-05",
    "capabilities": {
      "tools": {
        "listChanged": false
      }
    },
    "serverInfo": {
      "name": "hermes-mcp-server",
      "version": "2.1.0"
    }
  }
}
```

**Notification:**
```json
{
  "jsonrpc": "2.0",
  "method": "notifications/initialized"
}
```

---

## 2. Tool Execution Payloads

### A. List Conversations (`conversations_list`)
Exposes all active messaging adapter channels and their associated session trackers.

**Request:**
```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "conversations_list",
    "arguments": {
      "limit": 5
    }
  },
  "id": 2
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "count": 1,
    "conversations": [
      {
        "session_key": "telegram:6308981865",
        "session_id": "20260606_124530_fa43b9",
        "platform": "telegram",
        "chat_type": "private",
        "display_name": "John Doe",
        "chat_name": "",
        "user_name": "johndoe",
        "updated_at": "2026-06-06T12:45:30.123456"
      }
    ]
  }
}
```

### B. Block-Wait for Events (`events_wait`)
Long-polling wait mechanism. Suspends the client connection until a change (such as a new response message or a security permission block) occurs.

**Request:**
```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "events_wait",
    "arguments": {
      "after_cursor": 0,
      "session_key": "telegram:6308981865",
      "timeout_ms": 30000
    }
  },
  "id": 3
}
```

**Response (Assistant message event):**
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "event": {
      "cursor": 142,
      "type": "message",
      "session_key": "telegram:6308981865",
      "session_id": "20260606_124530_fa43b9",
      "role": "assistant",
      "content": "Here is the implemented code structure...",
      "timestamp": "2026-06-06T12:46:02.987654"
    }
  }
}
```

**Response (Approval requested event):**
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "event": {
      "cursor": 143,
      "type": "approval_requested",
      "session_key": "telegram:6308981865",
      "session_id": "20260606_124530_fa43b9",
      "approval_id": "app_f12a3d",
      "data": {
        "command": "rm -rf build/",
        "risk": "high"
      },
      "timestamp": "2026-06-06T12:46:10.112233"
    }
  }
}
```

---

## 3. Real-World Integration Bug Fixes (Win32)

### A. The `clean_output` Markdown Table Corruption Bug
* **Symptom:** When reading responses over MCP, the harness was stripping out columns of tables and omitting lines with custom dividers (e.g. diagrams starting with box characters `│`).
* **Root Cause:** Raw subprocess execution output contains dirty ANSI escape codes and terminal borders which need cleanup, but MCP database message queries return **clean markdown**. Running `clean_output` on clean database transcripts corrupted tables.
* **Resolution:** Conditionally bypass cleanup based on execution context:
  ```python
  if self.use_cli_fallback:
      # Terminal stdout was captured -> needs strip of box lines / ANSI
      cleaned_reply = clean_output(stdout)
  else:
      # Native MCP message from database -> preserve markdown raw
      cleaned_reply = stdout
  ```

### B. Dynamic Windows Path Resolution
* **Symptom:** Hardcoding active paths like `C:\Users\admin\...` into python scripts caused execution crashes on any pipeline or other user machine.
* **Resolution:** Dynamically build directories with runtime parameters and keep the fallback system robust:
  ```python
  _local_appdata = os.environ.get("LOCALAPPDATA", r"C:\Users\admin\AppData\Local")
  _user_profile = os.environ.get("USERPROFILE", r"C:\Users\admin")

  DEFAULT_HERMES_PATH = os.path.join(_local_appdata, "hermes", "hermes-agent", "venv", "Scripts", "hermes.exe")
  if not os.path.exists(DEFAULT_HERMES_PATH):
      DEFAULT_HERMES_PATH = r"C:\Users\admin\AppData\Local\hermes\hermes-agent\venv\Scripts\hermes.exe"
  ```
