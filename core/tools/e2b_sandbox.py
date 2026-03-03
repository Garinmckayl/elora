"""
E2B Code Execution Sandbox
Gives Elora the ability to run Python (and JS) code securely in an isolated cloud sandbox.
Requires: pip install e2b-code-interpreter
API key env var: E2B_API_KEY
"""

import os
import logging

logger = logging.getLogger("elora.e2b")

E2B_API_KEY = os.getenv("E2B_API_KEY", "")


def run_code(language: str, code: str, timeout: int = 30) -> dict:
    """
    Execute code in a secure E2B cloud sandbox and return stdout/stderr/results.

    Args:
        language: Programming language - 'python' or 'javascript' (or 'js').
        code:     The code to execute.
        timeout:  Max execution time in seconds (default 30, max 120).

    Returns:
        dict: {
            status: 'success' | 'error',
            stdout: str,
            stderr: str,
            results: list of cell output objects (for Jupyter-style output),
            error: str | None  (exception message if execution failed),
        }
    """
    if not E2B_API_KEY:
        return {
            "status": "error",
            "stdout": "",
            "stderr": "",
            "results": [],
            "error": "E2B_API_KEY not configured. Set the environment variable to enable code execution.",
        }

    lang = language.lower().strip()
    if lang in ("js", "node", "nodejs"):
        lang = "javascript"
    if lang not in ("python", "javascript"):
        return {
            "status": "error",
            "stdout": "",
            "stderr": "",
            "results": [],
            "error": f"Unsupported language '{language}'. Use 'python' or 'javascript'.",
        }

    timeout = min(max(timeout, 5), 120)

    try:
        from e2b_code_interpreter import Sandbox

        with Sandbox(api_key=E2B_API_KEY, timeout=timeout + 10) as sandbox:
            if lang == "python":
                execution = sandbox.run_code(code, timeout=timeout)
            else:
                # For JavaScript, use the JS kernel
                execution = sandbox.run_code(code, language="js", timeout=timeout)

            # Collect text results
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
                    # Keep traceback concise — last 5 lines
                    tb_lines = execution.error.traceback.strip().splitlines()
                    error_msg += "\n" + "\n".join(tb_lines[-5:])

            if error_msg:
                logger.info(f"[E2B] Code error: {error_msg[:200]}")
                return {
                    "status": "error",
                    "stdout": stdout,
                    "stderr": stderr,
                    "results": results_text,
                    "error": error_msg,
                }

            logger.info(f"[E2B] Code executed OK: stdout={len(stdout)}c results={len(results_text)}")
            return {
                "status": "success",
                "stdout": stdout,
                "stderr": stderr,
                "results": results_text,
                "error": None,
            }

    except ImportError:
        return {
            "status": "error",
            "stdout": "",
            "stderr": "",
            "results": [],
            "error": "e2b-code-interpreter package not installed. Add it to requirements.txt.",
        }
    except Exception as e:
        logger.error(f"[E2B] Sandbox error: {e}", exc_info=True)
        return {
            "status": "error",
            "stdout": "",
            "stderr": "",
            "results": [],
            "error": str(e),
        }
