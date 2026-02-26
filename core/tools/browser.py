"""
Browser tools for Elora.

Two tiers:
  web_fetch    -- Fast, read-only. httpx + readability. No JS, no interaction.
                  Use for: reading articles, scraping prices, summarising pages.

  browser_task -- Full computer use. Headless Playwright + gemini-2.5-computer-use-preview
                  screenshot loop. Streams screenshots back over the caller-supplied
                  websocket so the phone UI can show a live browser view.
                  Use for: logging in, filling forms, booking tickets, anything interactive.
"""

from __future__ import annotations

import asyncio
import base64
import html
import json
import logging
import os
import re
from typing import AsyncIterator, Callable, Awaitable
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("elora.browser")

# Sensitive action names whose args should be partially redacted in logs
_SENSITIVE_ACTIONS = {"type_text_at"}


def _safe_log_args(name: str, args: dict) -> dict:
    """Return a copy of args safe to log -- redacts text content for sensitive actions."""
    if name not in _SENSITIVE_ACTIONS:
        return args
    safe = dict(args)
    if "text" in safe:
        raw = str(safe["text"])
        safe["text"] = raw[:2] + "***" if len(raw) > 2 else "***"
    return safe


# Per-user semaphores: at most one concurrent browser session per user.
# Keys are user_id strings; values are asyncio.Semaphore(1).
_user_browser_semaphores: dict[str, asyncio.Semaphore] = {}

# Per-user persistent Playwright BrowserContext (cookie/session isolation).
# Each user gets their own context so their logins, cookies, and sessions
# are completely separate from other users.
# Keys are user_id strings; values are Playwright BrowserContext objects.
_user_browser_contexts: dict[str, object] = {}
_user_browsers: dict[str, object] = {}  # underlying Browser instance per user


def _get_user_semaphore(user_id: str) -> asyncio.Semaphore:
    if user_id not in _user_browser_semaphores:
        _user_browser_semaphores[user_id] = asyncio.Semaphore(1)
    return _user_browser_semaphores[user_id]


async def _get_or_create_context(pw, user_id: str):
    """
    Return the persistent BrowserContext for user_id, creating it if needed.
    Each user gets their own isolated context (cookies, storage, sessions).
    """
    if user_id not in _user_browsers or _user_browsers[user_id] is None:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-extensions",
                "--disable-background-networking",
            ],
        )
        _user_browsers[user_id] = browser

        context = await browser.new_context(
            viewport={"width": VIEWPORT_W, "height": VIEWPORT_H},
            user_agent=USER_AGENT,
        )
        _user_browser_contexts[user_id] = context
        logger.info(f"[browser] Created new isolated context for user={user_id}")
    elif user_id not in _user_browser_contexts:
        browser = _user_browsers[user_id]
        context = await browser.new_context(
            viewport={"width": VIEWPORT_W, "height": VIEWPORT_H},
            user_agent=USER_AGENT,
        )
        _user_browser_contexts[user_id] = context

    return _user_browser_contexts[user_id]


async def clear_browser_session(user_id: str):
    """
    Destroy the persistent browser context for a user (logout / fresh start).
    Called if the user asks to "clear my browser" or "log out of everything".
    """
    ctx = _user_browser_contexts.pop(user_id, None)
    if ctx:
        try:
            await ctx.close()
        except Exception:
            pass
    browser = _user_browsers.pop(user_id, None)
    if browser:
        try:
            await browser.close()
        except Exception:
            pass
    logger.info(f"[browser] Cleared session for user={user_id}")

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
MAX_REDIRECTS = 5
MAX_FETCH_CHARS = 40_000


def _validate_url(url: str) -> tuple[bool, str]:
    """Reject non-http(s) and URLs without a domain."""
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            return False, f"Only http/https allowed, got '{p.scheme or 'none'}'"
        if not p.netloc:
            return False, "Missing domain"
        return True, ""
    except Exception as e:
        return False, str(e)


def _strip_tags(text: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", "", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _to_markdown(raw_html: str) -> str:
    """Best-effort HTML → markdown conversion (no extra deps)."""
    text = re.sub(
        r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>',
        lambda m: f"[{_strip_tags(m.group(2))}]({m.group(1)})",
        raw_html, flags=re.I,
    )
    text = re.sub(
        r'<h([1-6])[^>]*>([\s\S]*?)</h\1>',
        lambda m: f'\n{"#" * int(m.group(1))} {_strip_tags(m.group(2))}\n',
        text, flags=re.I,
    )
    text = re.sub(r"<li[^>]*>([\s\S]*?)</li>", lambda m: f"\n- {_strip_tags(m.group(1))}", text, flags=re.I)
    text = re.sub(r"</(p|div|section|article)>", "\n\n", text, flags=re.I)
    text = re.sub(r"<(br|hr)\s*/?>", "\n", text, flags=re.I)
    text = _strip_tags(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Tier 1 -- web_fetch
# ---------------------------------------------------------------------------

async def web_fetch(url: str, extract_mode: str = "markdown", max_chars: int = MAX_FETCH_CHARS) -> dict:
    """
    Fetch a URL and extract readable content.

    Returns a dict with keys: status, url, title, text, truncated, error.
    No JS execution — pure HTTP. Fast and cheap.
    """
    ok, err = _validate_url(url)
    if not ok:
        return {"status": "error", "url": url, "error": err, "text": ""}

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            max_redirects=MAX_REDIRECTS,
            timeout=20.0,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        final_url = str(resp.url)
        ctype = resp.headers.get("content-type", "")
        title = ""

        if "application/json" in ctype:
            text = json.dumps(resp.json(), indent=2, ensure_ascii=False)
        elif "text/html" in ctype or resp.text[:256].lower().lstrip().startswith(("<!doctype", "<html")):
            # Extract <title>
            m = re.search(r"<title[^>]*>(.*?)</title>", resp.text, re.I | re.S)
            title = _strip_tags(m.group(1)).strip() if m else ""

            # Try readability if available, otherwise fall back to regex
            try:
                from readability import Document
                doc = Document(resp.text)
                title = title or doc.title()
                raw = doc.summary()
            except ImportError:
                raw = resp.text

            text = _to_markdown(raw) if extract_mode == "markdown" else _strip_tags(raw)
            if title:
                text = f"# {title}\n\n{text}"
        else:
            text = resp.text

        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars] + "\n\n[... content truncated ...]"

        logger.info(f"[web_fetch] {url} -> {len(text)} chars, truncated={truncated}")
        return {
            "status": "success",
            "url": final_url,
            "title": title,
            "text": text,
            "truncated": truncated,
            "error": "",
        }

    except httpx.HTTPStatusError as e:
        return {"status": "error", "url": url, "error": f"HTTP {e.response.status_code}", "text": ""}
    except Exception as e:
        logger.error(f"[web_fetch] Error fetching {url}: {e}")
        return {"status": "error", "url": url, "error": str(e), "text": ""}


# ---------------------------------------------------------------------------
# Tier 2 -- browser_task (Gemini computer use + Playwright)
# ---------------------------------------------------------------------------

COMPUTER_USE_MODEL = os.getenv(
    "ELORA_COMPUTER_USE_MODEL",
    "gemini-2.5-computer-use-preview-10-2025",
)

# Viewport used for all browser sessions
VIEWPORT_W = 1280
VIEWPORT_H = 800

# Maximum screenshot loop iterations per task (safety cap)
MAX_ITERATIONS = 40

# Predefined Gemini computer-use function names that return screenshots
_CU_FUNCTIONS = {
    "open_web_browser", "click_at", "hover_at", "type_text_at",
    "scroll_document", "scroll_at", "wait_5_seconds", "go_back",
    "go_forward", "search", "navigate", "key_combination", "drag_and_drop",
}

# Max screenshot turns to keep in context (older ones get stripped to save tokens)
MAX_SCREENSHOT_TURNS = 3


async def browser_task(
    task: str,
    start_url: str = "https://www.google.com",
    on_screenshot: Callable[[bytes, str], Awaitable[None]] | None = None,
    on_step: Callable[[str], Awaitable[None]] | None = None,
    user_id: str = "anonymous",
) -> dict:
    """
    Execute a browser task using Gemini computer use + headless Playwright.

    Args:
        task:           Natural-language instruction (e.g. "find flights to Dubai under $500").
        start_url:      Initial URL to open before the agent starts.
        on_screenshot:  Async callback(png_bytes, current_url) called after each action.
                        Use this to stream frames to the WebSocket client.
        on_step:        Async callback(text) called with the model's reasoning at each step.

    Returns:
        dict with keys: status, result, steps, final_url, error
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {
            "status": "error",
            "result": "",
            "error": "Playwright not installed. Add 'playwright' to requirements.txt and run 'playwright install chromium'.",
            "steps": 0,
            "final_url": start_url,
        }

    try:
        from google import genai
        from google.genai import types as gtypes
    except ImportError:
        return {
            "status": "error",
            "result": "",
            "error": "google-genai not installed.",
            "steps": 0,
            "final_url": start_url,
        }

    api_key = os.getenv("GOOGLE_API_KEY", "")
    client = genai.Client(
        api_key=api_key,
        http_options={"api_version": "v1beta"},
    )

    # ------------------------------------------------------------------
    # Playwright helpers (async)
    # ------------------------------------------------------------------

    async def _screenshot(page) -> bytes:
        """Take a viewport screenshot and return raw PNG bytes."""
        return await page.screenshot(type="png", full_page=False)

    async def _current_state(page) -> tuple[bytes, str]:
        """Return (screenshot_png, current_url)."""
        await page.wait_for_load_state("domcontentloaded", timeout=10_000)
        await asyncio.sleep(0.4)  # let JS settle
        png = await _screenshot(page)
        url = page.url
        return png, url

    # ------------------------------------------------------------------
    # Action dispatcher: Gemini function_call → Playwright action
    # ------------------------------------------------------------------

    def _denorm_x(x: int) -> int:
        return int(x / 1000 * VIEWPORT_W)

    def _denorm_y(y: int) -> int:
        return int(y / 1000 * VIEWPORT_H)

    async def _dispatch(page, fc) -> tuple[bytes, str]:
        name = fc.name
        args = fc.args or {}

        if name == "open_web_browser":
            pass  # already open

        elif name == "navigate":
            raw = args.get("url", "https://www.google.com")
            url = raw if raw.startswith(("http://", "https://")) else f"https://{raw}"
            await page.goto(url, timeout=30_000)

        elif name == "click_at":
            await page.mouse.click(_denorm_x(args["x"]), _denorm_y(args["y"]))

        elif name == "hover_at":
            await page.mouse.move(_denorm_x(args["x"]), _denorm_y(args["y"]))

        elif name == "type_text_at":
            x, y = _denorm_x(args["x"]), _denorm_y(args["y"])
            await page.mouse.click(x, y)
            if args.get("clear_before_typing", True):
                await page.keyboard.press("Control+A")
                await page.keyboard.press("Delete")
            await page.keyboard.type(args.get("text", ""))
            if args.get("press_enter", False):
                await page.keyboard.press("Enter")

        elif name == "scroll_document":
            direction = args.get("direction", "down")
            key = {"down": "PageDown", "up": "PageUp"}.get(direction, "PageDown")
            await page.keyboard.press(key)

        elif name == "scroll_at":
            x, y = _denorm_x(args["x"]), _denorm_y(args["y"])
            direction = args.get("direction", "down")
            magnitude = int(args.get("magnitude", 800))
            dy = magnitude if direction == "down" else -magnitude if direction == "up" else 0
            dx = magnitude if direction == "right" else -magnitude if direction == "left" else 0
            await page.mouse.move(x, y)
            await page.mouse.wheel(dx, dy)

        elif name == "key_combination":
            keys_raw: str = args.get("keys", "")
            keys = [k.strip() for k in keys_raw.split("+") if k.strip()]
            for k in keys[:-1]:
                await page.keyboard.down(k)
            await page.keyboard.press(keys[-1])
            for k in reversed(keys[:-1]):
                await page.keyboard.up(k)

        elif name == "go_back":
            await page.go_back(timeout=10_000)

        elif name == "go_forward":
            await page.go_forward(timeout=10_000)

        elif name == "search":
            await page.goto("https://www.google.com", timeout=15_000)

        elif name == "wait_5_seconds":
            await asyncio.sleep(5)

        elif name == "drag_and_drop":
            x, y = _denorm_x(args["x"]), _denorm_y(args["y"])
            dx, dy = _denorm_x(args["destination_x"]), _denorm_y(args["destination_y"])
            await page.mouse.move(x, y)
            await page.mouse.down()
            await page.mouse.move(dx, dy)
            await page.mouse.up()

        return await _current_state(page)

    # ------------------------------------------------------------------
    # Gemini computer-use config
    # ------------------------------------------------------------------

    cu_config = gtypes.GenerateContentConfig(
        temperature=1.0,
        top_p=0.95,
        max_output_tokens=8192,
        tools=[
            gtypes.Tool(
                computer_use=gtypes.ComputerUse(
                    environment=gtypes.Environment.ENVIRONMENT_BROWSER,
                ),
            ),
        ],
        thinking_config=gtypes.ThinkingConfig(include_thoughts=True),
    )

    # ------------------------------------------------------------------
    # Main agent loop -- acquire per-user semaphore to prevent concurrent
    # browser sessions for the same user clobbering each other.
    # ------------------------------------------------------------------

    semaphore = _get_user_semaphore(user_id)
    async with semaphore:
        async with async_playwright() as pw:
            # Use per-user persistent context (isolated cookies/sessions per user)
            context = await _get_or_create_context(pw, user_id)

            # Single-tab enforcement: new tabs get redirected to current page
            page = await context.new_page()

            async def _handle_popup(new_page):
                new_url = new_page.url
                await new_page.close()
                await page.goto(new_url)

            context.on("page", lambda p: asyncio.create_task(_handle_popup(p)))

            steps = 0
            try:
                await page.goto(start_url, timeout=20_000)
                init_png, init_url = await _current_state(page)

                if on_screenshot:
                    await on_screenshot(init_png, init_url)

                # Build initial conversation: task + first screenshot
                contents = [
                    gtypes.Content(
                        role="user",
                        parts=[
                            gtypes.Part.from_text(text=task),
                        ],
                    )
                ]

                final_result = ""
                final_url = init_url

                for iteration in range(MAX_ITERATIONS):
                    # Call Gemini
                    try:
                        response = await asyncio.to_thread(
                            client.models.generate_content,
                            model=COMPUTER_USE_MODEL,
                            contents=contents,
                            config=cu_config,
                        )
                    except Exception as e:
                        logger.error(f"[browser_task] Gemini error on iter {iteration}: {e}")
                        break

                    if not response.candidates:
                        logger.warning("[browser_task] Empty response from Gemini")
                        break

                    candidate = response.candidates[0]
                    if candidate.content:
                        contents.append(candidate.content)

                    # Extract reasoning text
                    reasoning = ""
                    function_calls = []
                    if candidate.content and candidate.content.parts:
                        for part in candidate.content.parts:
                            if part.text:
                                reasoning += part.text
                            if part.function_call:
                                function_calls.append(part.function_call)

                    # Clean up thinking tags
                    reasoning = re.sub(r"<think>[\s\S]*?</think>", "", reasoning).strip()

                    if reasoning and on_step:
                        await on_step(reasoning)

                    # No more function calls → task complete
                    if not function_calls:
                        final_result = reasoning
                        logger.info(f"[browser_task] Done after {iteration + 1} iterations")
                        break

                    # Execute all function calls, collect screenshots
                    function_responses = []
                    for fc in function_calls:
                        # Redact sensitive args (e.g. passwords typed into forms)
                        logger.info(f"[browser_task] Action: {fc.name}({_safe_log_args(fc.name, dict(fc.args or {}))})")
                        steps += 1

                        if fc.name not in _CU_FUNCTIONS:
                            # Unknown tool — skip gracefully
                            function_responses.append(
                                gtypes.FunctionResponse(
                                    id=fc.id,
                                    name=fc.name,
                                    response={"error": f"Unknown action: {fc.name}"},
                                )
                            )
                            continue

                        png, current_url = await _dispatch(page, fc)
                        final_url = current_url

                        # Stream screenshot to WebSocket
                        if on_screenshot:
                            await on_screenshot(png, current_url)

                        function_responses.append(
                            gtypes.FunctionResponse(
                                id=fc.id,
                                name=fc.name,
                                response={"url": current_url},
                                parts=[
                                    gtypes.FunctionResponsePart(
                                        inline_data=gtypes.FunctionResponseBlob(
                                            mime_type="image/png",
                                            data=png,
                                        )
                                    )
                                ],
                            )
                        )

                    # Append function responses
                    contents.append(
                        gtypes.Content(
                            role="user",
                            parts=[gtypes.Part(function_response=fr) for fr in function_responses],
                        )
                    )

                    # Trim old screenshots to save context window
                    _trim_old_screenshots(contents)

                logger.info(f"[browser_task] Completed: steps={steps}, url={final_url}")
                return {
                    "status": "success",
                    "result": final_result or f"Task completed after {steps} browser actions.",
                    "steps": steps,
                    "final_url": final_url,
                    "error": "",
                }

            except Exception as e:
                logger.error(f"[browser_task] Unexpected error: {e}", exc_info=True)
                return {
                    "status": "error",
                    "result": "",
                    "steps": steps,
                    "final_url": page.url if page else start_url,
                    "error": str(e),
                }
            finally:
                # Only close the page — keep the context alive for cookie persistence
                try:
                    await page.close()
                except Exception:
                    pass
                # Note: context and browser are kept alive in _user_browser_contexts
                # for cookie/session persistence across tasks for this user.


def _trim_old_screenshots(contents: list) -> None:
    """
    Remove inline screenshot data from old turns to keep context window small.
    Only keep screenshots from the last MAX_SCREENSHOT_TURNS turns.
    """
    screenshot_turns_found = 0
    for content in reversed(contents):
        if content.role != "user" or not content.parts:
            continue
        has_screenshot = any(
            getattr(p, "function_response", None) and
            getattr(p.function_response, "name", None) in _CU_FUNCTIONS
            for p in content.parts
        )
        if not has_screenshot:
            continue
        screenshot_turns_found += 1
        if screenshot_turns_found > MAX_SCREENSHOT_TURNS:
            for p in content.parts:
                fr = getattr(p, "function_response", None)
                if fr and getattr(fr, "name", None) in _CU_FUNCTIONS:
                    fr.parts = None  # strip the image data
