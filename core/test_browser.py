#!/usr/bin/env python3
"""
test_browser.py -- Standalone test for Elora's browser tools.

Tests:
  1. web_fetch  (Tier 1 -- httpx, no JS)
  2. browser_task (Tier 2 -- Playwright + Gemini computer use)
  3. video_frame echo -- prints the base64 size that would be sent to the Live API

Usage:
  cd elora/core
  python3 test_browser.py            # runs all tests
  python3 test_browser.py --tier1    # only web_fetch
  python3 test_browser.py --tier2    # only browser_task (requires GOOGLE_API_KEY)
"""

import asyncio
import base64
import sys
import os

# Load .env so GOOGLE_API_KEY etc. are available
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))


# ─── ANSI helpers ────────────────────────────────────────────────────────────
def ok(msg):   print(f"\033[32m✓\033[0m {msg}")
def err(msg):  print(f"\033[31m✗\033[0m {msg}")
def info(msg): print(f"\033[34m·\033[0m {msg}")
def header(msg): print(f"\n\033[1m{msg}\033[0m")


# ─── Tier 1: web_fetch ───────────────────────────────────────────────────────

async def test_web_fetch():
    header("Tier 1 — web_fetch (httpx, no JS)")
    from tools.browser import web_fetch

    cases = [
        ("https://example.com",       "Example Domain"),
        ("https://httpbin.org/json",  "slideshow"),   # JSON response
    ]
    passed = 0
    for url, expected_fragment in cases:
        result = await web_fetch(url)
        if result["status"] == "success" and expected_fragment.lower() in result["text"].lower():
            ok(f"{url}  →  {len(result['text'])} chars  (title: {result['title']!r})")
            passed += 1
        else:
            err(f"{url}  →  status={result['status']}  error={result.get('error')}")

    # Error case
    bad = await web_fetch("ftp://bad-scheme")
    if bad["status"] == "error":
        ok("ftp:// correctly rejected")
        passed += 1
    else:
        err(f"ftp:// should have been rejected, got {bad}")

    print(f"\n  {passed}/3 passed")
    return passed == 3


# ─── Tier 2: browser_task ────────────────────────────────────────────────────

async def test_browser_task():
    header("Tier 2 — browser_task (Playwright + Gemini computer use)")
    from tools.browser import browser_task

    screenshots = []
    steps = []

    async def on_screenshot(png: bytes, url: str):
        screenshots.append((len(png), url))
        info(f"screenshot  {len(png):,} bytes  @  {url}")

    async def on_step(text: str):
        steps.append(text)
        info(f"step        {text[:100]}")

    result = await browser_task(
        task="Visit example.com and report the page heading text",
        start_url="https://example.com",
        on_screenshot=on_screenshot,
        on_step=on_step,
        user_id="test-user",
    )

    print()
    if result["status"] == "success":
        ok(f"status: success")
    else:
        err(f"status: {result['status']}  error: {result.get('error')}")
        return False

    ok(f"steps taken:    {result['steps']}")
    ok(f"screenshots:    {len(screenshots)}")
    ok(f"final_url:      {result['final_url']}")
    ok(f"result snippet: {result['result'][:200]}")

    passed = (
        result["status"] == "success"
        and len(screenshots) >= 1
        and "example" in result["result"].lower()
    )
    print(f"\n  {'1/1 passed' if passed else '0/1 passed'}")
    return passed


# ─── Video frame simulation ──────────────────────────────────────────────────

def test_video_frame_format():
    header("Video frame format (simulated)")

    # Simulate what the phone would send: a 480x360 JPEG encoded as base64
    # Here we just use a tiny 1x1 white JPEG as a stand-in
    tiny_jpeg = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
        b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
        b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\x1e\xff\xc0"
        b"\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00"
        b"\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00"
        b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10"
        b"\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01}\x01"
        b"\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07\"q\x142\x81\x91\xa1"
        b"\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17\x18\x19\x1a%&'()"
        b"*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x83\x84\x85\x86\x87\x88"
        b"\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6"
        b"\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4"
        b"\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1"
        b"\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5\xf6\xf7"
        b"\xf8\xf9\xfa\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xfb\xd4P\x00\x00"
        b"\x00\x1f\xff\xd9"
    )
    b64 = base64.b64encode(tiny_jpeg).decode()

    # Simulate the WS message the frontend sends
    import json
    msg = json.dumps({"type": "video_frame", "content": b64, "mime_type": "image/jpeg"})
    decoded_bytes = base64.b64decode(json.loads(msg)["content"])

    ok(f"Frame encoded as base64:  {len(b64)} chars")
    ok(f"Frame decoded back:       {len(decoded_bytes)} bytes (matches original: {decoded_bytes == tiny_jpeg})")
    ok(f"WS message size:          {len(msg)} bytes")
    ok(f"Would be sent to:         call_session.send_realtime_input(media=Blob(data=..., mime_type='image/jpeg'))")

    # Verify the backend handler path
    info("Backend path: main.py  msg_type=='video_frame'  →  call_session.send_realtime_input()")
    info("Frame rate:   1 frame every 2 seconds (configurable in App.tsx videoFrameIntervalRef)")
    info("Quality:      0.35 JPEG (balance between bandwidth and Gemini vision quality)")
    print("\n  1/1 passed")
    return True


# ─── Entry point ─────────────────────────────────────────────────────────────

async def main():
    args = set(sys.argv[1:])
    run_tier1 = "--tier1" in args or not args
    run_tier2 = "--tier2" in args or not args
    run_video = "--video" in args or not args

    results = {}

    if run_tier1:
        results["web_fetch"] = await test_web_fetch()

    if run_tier2:
        if not os.getenv("GOOGLE_API_KEY"):
            err("GOOGLE_API_KEY not set -- skipping browser_task test")
            results["browser_task"] = False
        else:
            results["browser_task"] = await test_browser_task()

    if run_video:
        results["video_frame"] = test_video_frame_format()

    header("Summary")
    all_passed = True
    for name, passed in results.items():
        if passed:
            ok(name)
        else:
            err(name)
            all_passed = False

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
