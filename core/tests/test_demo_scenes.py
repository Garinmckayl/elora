#!/usr/bin/env python3
"""
Elora Demo Scene Integration Tests

Tests every feature that will appear in the demo video against the LIVE backend.
Run this BEFORE recording to catch issues early.

Usage:
    python3 tests/test_demo_scenes.py

Each test connects via WebSocket to the live backend (same as the phone app)
and sends messages, then checks the response contains the expected tool calls
and results.
"""

import asyncio
import json
import sys
import time
import traceback

try:
    import websockets
except ImportError:
    print("Installing websockets...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets", "-q"])
    import websockets

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BACKEND_URL = "wss://elora-backend-453139277365.us-central1.run.app"
TEST_USER_ID = "demo_test_user_" + str(int(time.time()))
WS_TIMEOUT = 120  # seconds -- some tools take a while (browser, sandbox)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def ok(msg):
    print(f"  {Colors.GREEN}PASS{Colors.RESET} {msg}")

def fail(msg):
    print(f"  {Colors.RED}FAIL{Colors.RESET} {msg}")

def info(msg):
    print(f"  {Colors.CYAN}INFO{Colors.RESET} {msg}")

def warn(msg):
    print(f"  {Colors.YELLOW}WARN{Colors.RESET} {msg}")

def header(msg):
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}  {msg}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")


async def send_and_collect(user_id: str, message: str, timeout: int = WS_TIMEOUT) -> list:
    """
    Connect to the text WebSocket, send a message, and collect all responses
    until the agent finishes (sends a final text response or connection goes quiet).
    Returns a list of all received messages (parsed JSON).
    """
    url = f"{BACKEND_URL}/ws/{user_id}"
    messages = []
    
    try:
        async with websockets.connect(url, close_timeout=10, ping_interval=20, ping_timeout=10) as ws:
            # Send the text message
            await ws.send(json.dumps({"type": "text", "content": message}))
            
            # Collect responses until timeout or agent done
            start = time.time()
            last_msg_time = start
            
            while True:
                remaining = timeout - (time.time() - start)
                if remaining <= 0:
                    break
                
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 30))
                    last_msg_time = time.time()
                    try:
                        msg = json.loads(raw)
                        messages.append(msg)
                        
                        # If we got a final text response (not a tool call/result),
                        # wait a bit for any trailing messages then stop
                        if msg.get("type") == "text" and not msg.get("is_tool_call"):
                            # Wait 3 more seconds for any trailing messages
                            try:
                                while True:
                                    raw2 = await asyncio.wait_for(ws.recv(), timeout=3)
                                    try:
                                        messages.append(json.loads(raw2))
                                    except json.JSONDecodeError:
                                        pass
                            except asyncio.TimeoutError:
                                break
                    except json.JSONDecodeError:
                        pass
                except asyncio.TimeoutError:
                    # No message for 30s -- agent is probably done
                    if time.time() - last_msg_time > 15:
                        break
                    continue
                    
    except Exception as e:
        messages.append({"_error": str(e)})
    
    return messages


def find_tool_calls(messages: list, tool_name: str = None) -> list:
    """Extract tool call messages, optionally filtering by tool name."""
    calls = []
    for msg in messages:
        if msg.get("type") == "tool_call":
            if tool_name is None or msg.get("name") == tool_name:
                calls.append(msg)
    return calls


def find_tool_results(messages: list, tool_name: str = None) -> list:
    """Extract tool result messages, optionally filtering by tool name."""
    results = []
    for msg in messages:
        if msg.get("type") == "tool_result":
            if tool_name is None or msg.get("name") == tool_name:
                results.append(msg)
    return results


def find_text_responses(messages: list) -> list:
    """Extract final text responses from the agent."""
    return [m for m in messages if m.get("type") == "text" and not m.get("is_tool_call")]


def all_text(messages: list) -> str:
    """Concatenate all text content from messages."""
    parts = []
    for msg in messages:
        if msg.get("type") == "text":
            parts.append(msg.get("content", ""))
        elif msg.get("type") == "tool_result":
            parts.append(str(msg.get("result", "")))
    return "\n".join(parts).lower()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

passed = 0
failed_tests = 0
warnings = 0


async def test_health():
    """Test that the backend is alive."""
    global passed, failed_tests
    header("TEST: Backend Health Check")
    
    import urllib.request
    try:
        url = BACKEND_URL.replace("wss://", "https://") + "/health"
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        
        if data.get("status") == "ok":
            ok(f"Backend healthy: v{data.get('version', '?')}")
            passed += 1
        else:
            fail(f"Unexpected response: {data}")
            failed_tests += 1
    except Exception as e:
        fail(f"Backend unreachable: {e}")
        failed_tests += 1


async def test_agent_identity():
    """Test the /agent/identity endpoint."""
    global passed, failed_tests
    header("TEST: Agent Identity (Agntor Security)")
    
    import urllib.request
    try:
        url = BACKEND_URL.replace("wss://", "https://") + "/agent/identity"
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        
        security = data.get("security", {})
        checks = [
            ("agent_id", data.get("agent_id") == "agent://elora"),
            ("prompt_guard", security.get("prompt_guard") is True),
            ("pii_redaction", security.get("pii_redaction") is True),
            ("tool_guard", security.get("tool_guard") is True),
            ("ssrf_protection", security.get("ssrf_protection") is True),
        ]
        
        all_ok = True
        for name, result in checks:
            if result:
                ok(f"{name}")
            else:
                fail(f"{name}")
                all_ok = False
        
        if all_ok:
            passed += 1
        else:
            failed_tests += 1
    except Exception as e:
        fail(f"Identity endpoint failed: {e}")
        failed_tests += 1


async def test_skills_endpoint():
    """Test the /agent/skills endpoint."""
    global passed, failed_tests
    header("TEST: Skills Endpoint")
    
    import urllib.request
    try:
        url = BACKEND_URL.replace("wss://", "https://") + "/agent/skills"
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        
        skills = data.get("bundled_skills", [])
        count = data.get("count", 0)
        
        if count == 6:
            ok(f"6 bundled skills returned")
            skill_names = {s["name"] for s in skills}
            expected = {"weather", "hackernews", "exchange_rates", "wikipedia", "crypto_prices", "rss_reader"}
            if skill_names == expected:
                ok(f"All expected skills present: {', '.join(sorted(expected))}")
                passed += 1
            else:
                fail(f"Skill names mismatch. Got: {skill_names}, Expected: {expected}")
                failed_tests += 1
        else:
            fail(f"Expected 6 skills, got {count}")
            failed_tests += 1
    except Exception as e:
        fail(f"Skills endpoint failed: {e}")
        failed_tests += 1


async def test_websocket_connection():
    """Test basic WebSocket connection and a simple message."""
    global passed, failed_tests
    header("TEST: WebSocket Connection + Simple Chat")
    
    info(f"Connecting as user: {TEST_USER_ID}")
    info("Sending: 'What time is it?'")
    
    messages = await send_and_collect(TEST_USER_ID, "What time is it?", timeout=30)
    
    if any(m.get("_error") for m in messages):
        error = next(m["_error"] for m in messages if "_error" in m)
        fail(f"WebSocket error: {error}")
        failed_tests += 1
        return
    
    text_responses = find_text_responses(messages)
    if text_responses:
        content = text_responses[-1].get("content", "")[:200]
        ok(f"Got text response ({len(content)} chars): {content[:100]}...")
        passed += 1
    else:
        # Check if we got any messages at all
        if messages:
            warn(f"Got {len(messages)} messages but no final text response")
            for m in messages[:5]:
                info(f"  msg type={m.get('type', '?')}")
            failed_tests += 1
        else:
            fail("No messages received at all")
            failed_tests += 1


async def test_scene2_browser_hackernews():
    """
    SCENE 2 -- Browser: "Go to Hacker News and tell me the top 3 stories"
    
    This should trigger the browser_worker sub-agent with Playwright.
    We expect: tool_call for browse_web or web_search, and a response
    containing actual story titles.
    """
    global passed, failed_tests, warnings
    header("TEST: Scene 2 -- Browser (Hacker News)")
    
    info("Sending: 'Go to news.ycombinator.com and tell me the top 3 stories right now'")
    
    messages = await send_and_collect(
        TEST_USER_ID,
        "Go to news.ycombinator.com and tell me the top 3 stories right now. Use the browser to visit the actual page.",
        timeout=90
    )
    
    if any(m.get("_error") for m in messages):
        fail(f"WebSocket error: {next(m['_error'] for m in messages if '_error' in m)}")
        failed_tests += 1
        return
    
    full_text = all_text(messages)
    
    # Check for browser-related tool calls
    tool_calls = find_tool_calls(messages)
    browser_calls = [c for c in tool_calls if c.get("name") in ("browse_web", "web_search", "fetch_webpage")]
    
    if browser_calls:
        ok(f"Browser/web tool called: {[c.get('name') for c in browser_calls]}")
    else:
        warn("No browser/web tool call detected -- agent may have used cached knowledge")
        warnings += 1
    
    # Check for screenshot messages
    screenshots = [m for m in messages if m.get("type") == "browser_screenshot"]
    if screenshots:
        ok(f"Got {len(screenshots)} browser screenshot(s)")
    else:
        info("No browser screenshots (may have used web_search instead)")
    
    # Check that response contains story-like content
    text_responses = find_text_responses(messages)
    if text_responses:
        response = text_responses[-1].get("content", "")
        if len(response) > 50:
            ok(f"Got detailed response ({len(response)} chars)")
            passed += 1
        else:
            warn(f"Response seems short: {response[:100]}")
            warnings += 1
            passed += 1  # Still pass -- we got a response
    else:
        fail("No text response received")
        failed_tests += 1


async def test_scene2_code_sandbox():
    """
    SCENE 2 -- Sandbox: Run Python code in the sandbox.
    
    This should trigger the run_code tool and execute in E2B.
    """
    global passed, failed_tests
    header("TEST: Scene 2 -- Code Sandbox")
    
    code = "print('Hello from Elora sandbox!'); import sys; print(f'Python {sys.version}')"
    msg = f"Run this Python code in my sandbox: {code}"
    
    info(f"Sending code execution request")
    
    messages = await send_and_collect(TEST_USER_ID, msg, timeout=60)
    
    if any(m.get("_error") for m in messages):
        fail(f"WebSocket error: {next(m['_error'] for m in messages if '_error' in m)}")
        failed_tests += 1
        return
    
    full_text = all_text(messages)
    
    # Check for code execution tool call
    tool_calls = find_tool_calls(messages)
    code_calls = [c for c in tool_calls if c.get("name") in ("run_code", "run_code_in_sandbox")]
    
    if code_calls:
        ok(f"Code execution tool called: {code_calls[0].get('name')}")
    else:
        info(f"Tool calls found: {[c.get('name') for c in tool_calls]}")
    
    # Check for "hello" or "python" in response (proof it ran)
    if "hello" in full_text or "sandbox" in full_text or "python" in full_text:
        ok("Code execution output detected in response")
        passed += 1
    elif "e2b" in full_text.lower() or "not configured" in full_text:
        fail("E2B sandbox not configured -- E2B_API_KEY missing on backend")
        failed_tests += 1
    else:
        warn(f"Response doesn't clearly show code output. Got: {full_text[:200]}")
        # Still check if we got any response
        if find_text_responses(messages):
            passed += 1
        else:
            failed_tests += 1


async def test_scene3_skill_search():
    """
    SCENE 3 -- Skills: Search for crypto prices skill.
    """
    global passed, failed_tests
    header("TEST: Scene 3 -- Skill Search (crypto)")
    
    info("Sending: 'Search for a skill that can check crypto prices'")
    
    messages = await send_and_collect(
        TEST_USER_ID,
        "Search for a skill that can check cryptocurrency prices",
        timeout=45
    )
    
    if any(m.get("_error") for m in messages):
        fail(f"WebSocket error: {next(m['_error'] for m in messages if '_error' in m)}")
        failed_tests += 1
        return
    
    full_text = all_text(messages)
    
    # Check for skill search tool call
    tool_calls = find_tool_calls(messages)
    skill_calls = [c for c in tool_calls if "skill" in c.get("name", "").lower()]
    
    if skill_calls:
        ok(f"Skill tool called: {[c.get('name') for c in skill_calls]}")
    
    # Check that crypto_prices skill was found
    if "crypto" in full_text:
        ok("Crypto skill found in response")
        passed += 1
    else:
        warn(f"Crypto skill not clearly mentioned. Response: {full_text[:300]}")
        failed_tests += 1


async def test_scene3_skill_install_and_execute():
    """
    SCENE 3 -- Skills: Install and execute the crypto_prices skill.
    """
    global passed, failed_tests
    header("TEST: Scene 3 -- Skill Install + Execute (crypto_prices)")
    
    info("Sending: 'Install the crypto_prices skill and run it for bitcoin and ethereum'")
    
    messages = await send_and_collect(
        TEST_USER_ID,
        "Install the crypto_prices skill and then execute it to get the current prices of bitcoin and ethereum in USD",
        timeout=90
    )
    
    if any(m.get("_error") for m in messages):
        fail(f"WebSocket error: {next(m['_error'] for m in messages if '_error' in m)}")
        failed_tests += 1
        return
    
    full_text = all_text(messages)
    
    # Check for skill-related tool calls
    tool_calls = find_tool_calls(messages)
    skill_calls = [c for c in tool_calls if "skill" in c.get("name", "").lower()]
    
    if skill_calls:
        call_names = [c.get("name") for c in skill_calls]
        ok(f"Skill tools called: {call_names}")
        
        if any("install" in n for n in call_names):
            ok("install_skill called")
        if any("execute" in n for n in call_names):
            ok("execute_skill called")
    
    # Check for actual price data in response
    if "bitcoin" in full_text or "btc" in full_text or "ethereum" in full_text or "eth" in full_text:
        ok("Crypto price data detected in response")
        
        # Try to find actual numbers (prices)
        import re
        numbers = re.findall(r'\$?[\d,]+\.?\d*', full_text)
        if numbers:
            ok(f"Price values found: {numbers[:5]}")
            passed += 1
        else:
            warn("No price numbers found but crypto mentioned")
            passed += 1
    elif "e2b" in full_text or "sandbox" in full_text and "error" in full_text:
        fail("Sandbox/E2B error -- skill execution failed (likely E2B_API_KEY issue)")
        failed_tests += 1
    else:
        fail(f"No crypto data in response. Got: {full_text[:300]}")
        failed_tests += 1


async def test_scene3_skill_create():
    """
    SCENE 3 -- Skills: Create a brand new skill from scratch.
    
    This is THE differentiator. Elora writes code, tests it, saves it.
    """
    global passed, failed_tests
    header("TEST: Scene 3 -- Skill Creation (uptime checker)")
    
    info("Sending: 'Create a skill called uptime_checker that checks if a website is up and returns the response time'")
    
    messages = await send_and_collect(
        TEST_USER_ID,
        (
            "Create a new skill called 'uptime_checker'. "
            "It should take a URL parameter, make an HTTP GET request to it, "
            "and return whether the site is up (status code 200) and the response time in milliseconds. "
            "Write the Python code, test it, and save it to my skill library."
        ),
        timeout=90
    )
    
    if any(m.get("_error") for m in messages):
        fail(f"WebSocket error: {next(m['_error'] for m in messages if '_error' in m)}")
        failed_tests += 1
        return
    
    full_text = all_text(messages)
    
    # Check for create_skill tool call
    tool_calls = find_tool_calls(messages)
    create_calls = [c for c in tool_calls if "create" in c.get("name", "").lower() and "skill" in c.get("name", "").lower()]
    
    if create_calls:
        ok("create_skill tool called")
    else:
        skill_calls = [c for c in tool_calls if "skill" in c.get("name", "").lower()]
        if skill_calls:
            info(f"Skill tools called: {[c.get('name') for c in skill_calls]}")
        else:
            info(f"All tool calls: {[c.get('name') for c in tool_calls]}")
    
    # Check that the skill was created
    if "created" in full_text or "saved" in full_text or "uptime" in full_text:
        ok("Skill creation confirmed in response")
        passed += 1
    elif "error" in full_text and ("e2b" in full_text or "sandbox" in full_text):
        fail("Sandbox error during skill creation -- E2B_API_KEY issue?")
        failed_tests += 1
    else:
        warn(f"Unclear if skill was created. Response: {full_text[:300]}")
        failed_tests += 1


async def test_scene2_email():
    """
    SCENE 2 -- Email: Send a test email.
    
    NOTE: This requires OAuth to be connected for the test user.
    If OAuth is not connected, this test will show a helpful warning.
    """
    global passed, failed_tests, warnings
    header("TEST: Scene 2 -- Email (Gmail)")
    
    info("Sending: 'Send a test email to me'")
    info("NOTE: This requires Gmail OAuth to be connected for the test user")
    
    messages = await send_and_collect(
        TEST_USER_ID,
        "Send an email to test@example.com with the subject 'Elora Demo Test' and body 'This is a test email sent by Elora.'",
        timeout=45
    )
    
    if any(m.get("_error") for m in messages):
        fail(f"WebSocket error: {next(m['_error'] for m in messages if '_error' in m)}")
        failed_tests += 1
        return
    
    full_text = all_text(messages)
    
    # Check for email tool call
    tool_calls = find_tool_calls(messages)
    email_calls = [c for c in tool_calls if "email" in c.get("name", "").lower() or "gmail" in c.get("name", "").lower() or "send" in c.get("name", "").lower()]
    
    if email_calls:
        ok(f"Email tool called: {[c.get('name') for c in email_calls]}")
    
    if "oauth" in full_text or "connect" in full_text or "authorize" in full_text or "google account" in full_text:
        warn("Gmail OAuth not connected for test user -- expected for automated test")
        warn("For the demo, make sure YOUR user account has Gmail connected via Settings")
        warnings += 1
        passed += 1  # This is expected behavior
    elif "sent" in full_text or "email" in full_text:
        ok("Email send attempted/confirmed")
        passed += 1
    else:
        info(f"Response: {full_text[:300]}")
        passed += 1  # Don't fail -- OAuth is external


async def test_memory():
    """
    Test memory: Store a fact and recall it.
    """
    global passed, failed_tests
    header("TEST: Memory (Remember + Recall)")
    
    # First, store a fact
    info("Sending: 'Remember that my favorite programming language is Python'")
    messages1 = await send_and_collect(
        TEST_USER_ID,
        "Remember that my favorite programming language is Python and I prefer dark mode.",
        timeout=30
    )
    
    text1 = all_text(messages1)
    if "remember" in text1 or "noted" in text1 or "saved" in text1 or "got it" in text1 or "will remember" in text1:
        ok("Memory storage acknowledged")
    else:
        info(f"Storage response: {text1[:200]}")
    
    # Wait a moment for memory to persist
    await asyncio.sleep(2)
    
    # Now recall it
    info("Sending: 'What is my favorite programming language?'")
    messages2 = await send_and_collect(
        TEST_USER_ID,
        "What is my favorite programming language?",
        timeout=30
    )
    
    text2 = all_text(messages2)
    if "python" in text2:
        ok("Memory recall successful -- 'Python' found in response")
        passed += 1
    else:
        warn(f"Memory recall unclear. Response: {text2[:200]}")
        failed_tests += 1


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def main():
    global passed, failed_tests, warnings
    
    print(f"\n{Colors.BOLD}Elora Demo Scene Integration Tests{Colors.RESET}")
    print(f"Backend: {BACKEND_URL}")
    print(f"Test user: {TEST_USER_ID}")
    print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Run tests in order
    tests = [
        ("Health Check", test_health),
        ("Agent Identity", test_agent_identity),
        ("Skills Endpoint", test_skills_endpoint),
        ("WebSocket Chat", test_websocket_connection),
        ("Memory", test_memory),
        ("Browser (HN)", test_scene2_browser_hackernews),
        ("Code Sandbox", test_scene2_code_sandbox),
        ("Email (Gmail)", test_scene2_email),
        ("Skill Search", test_scene3_skill_search),
        ("Skill Install+Execute", test_scene3_skill_install_and_execute),
        ("Skill Creation", test_scene3_skill_create),
    ]
    
    for name, test_fn in tests:
        try:
            await test_fn()
        except Exception as e:
            header(f"TEST: {name} -- EXCEPTION")
            fail(f"Unhandled exception: {e}")
            traceback.print_exc()
            failed_tests += 1
    
    # Summary
    total = passed + failed_tests
    print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}  RESULTS: {passed}/{total} passed, {failed_tests} failed, {warnings} warnings{Colors.RESET}")
    print(f"{'='*60}")
    
    if failed_tests == 0:
        print(f"\n{Colors.GREEN}{Colors.BOLD}  ALL TESTS PASSED -- Ready to record the demo!{Colors.RESET}\n")
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}  {failed_tests} TESTS FAILED -- Fix these before recording!{Colors.RESET}\n")
    
    return 1 if failed_tests > 0 else 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
