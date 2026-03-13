"""
Per-user persistent sandbox manager using E2B.

Each user gets their own isolated E2B sandbox that persists across sessions.
Sandboxes auto-pause when idle and resume on next use. This gives every user
their own personal compute environment where skills run, packages persist,
and files survive across conversations.
"""

import os
import logging
import time
from typing import Optional

logger = logging.getLogger("elora.sandbox")

E2B_API_KEY = os.getenv("E2B_API_KEY", "")

# In-memory cache of active sandbox connections (user_id -> sandbox instance)
_active_sandboxes: dict[str, object] = {}
# Track last activity per user for cleanup
_last_activity: dict[str, float] = {}


def _get_firestore():
    """Lazy Firestore client."""
    from google.cloud import firestore
    return firestore.Client()


def _get_sandbox_doc(user_id: str):
    """Get the Firestore document reference for a user's sandbox metadata."""
    db = _get_firestore()
    return db.collection("users").document(user_id).collection("sandbox").document("primary")


def get_or_create_sandbox(user_id: str):
    """
    Get an existing sandbox for the user, or create a new one.
    Uses E2B's auto-pause feature so sandboxes survive between sessions.
    Returns the sandbox instance ready for use.
    """
    if not E2B_API_KEY:
        return None

    # Check in-memory cache first
    if user_id in _active_sandboxes:
        try:
            sbx = _active_sandboxes[user_id]
            # Quick health check - if this fails, sandbox is dead
            sbx.files.list("/")
            _last_activity[user_id] = time.time()
            return sbx
        except Exception:
            logger.info(f"[Sandbox] Cached sandbox for {user_id} is stale, reconnecting")
            _active_sandboxes.pop(user_id, None)

    # Check Firestore for a paused/running sandbox ID
    try:
        doc = _get_sandbox_doc(user_id)
        snap = doc.get()
        if snap.exists:
            data = snap.to_dict()
            sandbox_id = data.get("sandbox_id")
            if sandbox_id:
                try:
                    from e2b_code_interpreter import Sandbox
                    logger.info(f"[Sandbox] Reconnecting to sandbox {sandbox_id} for {user_id}")
                    sbx = Sandbox.connect(sandbox_id, api_key=E2B_API_KEY, timeout=300)
                    _active_sandboxes[user_id] = sbx
                    _last_activity[user_id] = time.time()
                    return sbx
                except Exception as e:
                    logger.warning(f"[Sandbox] Failed to reconnect to {sandbox_id}: {e}")
                    # Sandbox is gone, will create new one below
    except Exception as e:
        logger.warning(f"[Sandbox] Firestore lookup failed: {e}")

    # Create a brand new sandbox with auto-pause
    try:
        from e2b_code_interpreter import Sandbox

        logger.info(f"[Sandbox] Creating new sandbox for {user_id}")
        sbx = Sandbox.beta_create(
            api_key=E2B_API_KEY,
            auto_pause=True,
            timeout=300,  # 5 min timeout before auto-pause
        )

        # Set up the sandbox environment
        sbx.run_code("""
import subprocess
subprocess.run(["pip", "install", "-q", "requests", "beautifulsoup4", "feedparser", "pyyaml"], 
               capture_output=True)
# Install git for repository operations
subprocess.run(["apt-get", "update", "-qq"], capture_output=True)
subprocess.run(["apt-get", "install", "-y", "-qq", "git"], capture_output=True)
print("Elora sandbox ready")
""")

        # Create workspace directories
        sbx.files.make_dir("/home/user/skills")
        sbx.files.make_dir("/home/user/workspace")
        sbx.files.make_dir("/home/user/data")

        # Persist sandbox ID to Firestore
        try:
            doc = _get_sandbox_doc(user_id)
            doc.set({
                "sandbox_id": sbx.sandbox_id,
                "created_at": time.time(),
                "status": "active",
            })
        except Exception as e:
            logger.warning(f"[Sandbox] Failed to persist sandbox ID: {e}")

        _active_sandboxes[user_id] = sbx
        _last_activity[user_id] = time.time()
        return sbx

    except ImportError:
        logger.error("[Sandbox] e2b_code_interpreter not installed")
        return None
    except Exception as e:
        logger.error(f"[Sandbox] Failed to create sandbox: {e}", exc_info=True)
        return None


def run_in_sandbox(user_id: str, code: str, language: str = "python", timeout: int = 30) -> dict:
    """
    Execute code in the user's personal sandbox.
    The sandbox persists -- packages installed stay installed, files stay on disk.
    """
    if not E2B_API_KEY:
        return {
            "status": "error",
            "stdout": "",
            "stderr": "",
            "error": "E2B_API_KEY not configured.",
        }

    lang = language.lower().strip()
    if lang in ("js", "node", "nodejs"):
        lang = "javascript"
    if lang not in ("python", "javascript"):
        return {
            "status": "error",
            "stdout": "",
            "stderr": "",
            "error": f"Unsupported language '{language}'. Use 'python' or 'javascript'.",
        }

    timeout = min(max(timeout, 5), 120)

    sbx = get_or_create_sandbox(user_id)
    if sbx is None:
        return {
            "status": "error",
            "stdout": "",
            "stderr": "",
            "error": "Failed to create or connect to sandbox.",
        }

    try:
        if lang == "python":
            execution = sbx.run_code(code, timeout=timeout)
        else:
            execution = sbx.run_code(code, language="js", timeout=timeout)

        results_text = []
        for r in (execution.results or []):
            if hasattr(r, "text") and r.text:
                results_text.append(r.text)
            elif hasattr(r, "html") and r.html:
                results_text.append(f"[HTML output: {len(r.html)} chars]")
            elif hasattr(r, "png") and r.png:
                results_text.append("[Image output (PNG)]")

        stdout = execution.logs.stdout if execution.logs else ""
        stderr = execution.logs.stderr if execution.logs else ""
        error_msg = None

        if execution.error:
            error_msg = f"{execution.error.name}: {execution.error.value}"
            if execution.error.traceback:
                tb_lines = execution.error.traceback.strip().splitlines()
                error_msg += "\n" + "\n".join(tb_lines[-5:])

        if error_msg:
            return {
                "status": "error",
                "stdout": stdout,
                "stderr": stderr,
                "results": results_text,
                "error": error_msg,
            }

        return {
            "status": "success",
            "stdout": stdout,
            "stderr": stderr,
            "results": results_text,
            "error": None,
        }

    except Exception as e:
        logger.error(f"[Sandbox] Execution error for {user_id}: {e}", exc_info=True)
        # If sandbox died mid-execution, clear cache so next call creates fresh one
        _active_sandboxes.pop(user_id, None)
        return {
            "status": "error",
            "stdout": "",
            "stderr": "",
            "error": str(e),
        }


def install_package(user_id: str, package: str, language: str = "python") -> dict:
    """Install a package in the user's sandbox. Persists across sessions."""
    if language == "python":
        code = f"""
import subprocess
result = subprocess.run(["pip", "install", "-q", "{package}"], capture_output=True, text=True)
if result.returncode == 0:
    print(f"Successfully installed {package}")
else:
    print(f"Failed: {{result.stderr}}")
"""
    else:
        code = f"""
const {{ execSync }} = require('child_process');
try {{
    execSync('npm install {package}', {{ stdio: 'pipe' }});
    console.log('Successfully installed {package}');
}} catch(e) {{
    console.log('Failed: ' + e.stderr.toString());
}}
"""
    return run_in_sandbox(user_id, code, language, timeout=60)


def list_sandbox_files(user_id: str, path: str = "/home/user") -> dict:
    """List files in the user's sandbox."""
    sbx = get_or_create_sandbox(user_id)
    if sbx is None:
        return {"status": "error", "error": "Sandbox unavailable"}

    try:
        entries = sbx.files.list(path)
        files = [{"name": e.name, "type": "dir" if e.is_dir else "file"} for e in entries]
        return {"status": "success", "path": path, "files": files}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def write_sandbox_file(user_id: str, path: str, content: str) -> dict:
    """Write a file to the user's sandbox."""
    sbx = get_or_create_sandbox(user_id)
    if sbx is None:
        return {"status": "error", "error": "Sandbox unavailable"}

    try:
        sbx.files.write(path, content)
        return {"status": "success", "path": path, "report": f"File written to {path}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def read_sandbox_file(user_id: str, path: str) -> dict:
    """Read a file from the user's sandbox."""
    sbx = get_or_create_sandbox(user_id)
    if sbx is None:
        return {"status": "error", "error": "Sandbox unavailable"}

    try:
        content = sbx.files.read(path)
        return {"status": "success", "path": path, "content": content}
    except Exception as e:
        return {"status": "error", "error": str(e)}
