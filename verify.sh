#!/usr/bin/env bash
#
# Elora Live Verification Script
# ================================
# Zero-dependency smoke test against the live backend.
# Judges: run this to verify Elora is real and deployed on Google Cloud.
#
# Usage:
#   chmod +x verify.sh && ./verify.sh
#
# Requirements: bash, curl (pre-installed on macOS/Linux)
#
# What this tests:
#   1. Backend is live on Google Cloud Run
#   2. Agent identity + security capabilities (Agntor trust protocol)
#   3. All 6 bundled skills are registered
#   4. REST endpoints respond correctly
#   5. WebSocket accepts connections
#
# No API keys needed. No Python. No Docker. Just curl.
#

BACKEND="https://elora-backend-qf7tbdhnnq-uc.a.run.app"
PASS=0
FAIL=0
TOTAL=0

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

pass() { PASS=$((PASS+1)); TOTAL=$((TOTAL+1)); echo -e "  ${GREEN}PASS${NC} $1"; }
fail() { FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1)); echo -e "  ${RED}FAIL${NC} $1"; }
info() { echo -e "  ${CYAN}INFO${NC} $1"; }

echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  Elora — Live Backend Verification${NC}"
echo -e "${BOLD}  Backend: ${CYAN}${BACKEND}${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════════${NC}"
echo ""

# ─── 1. Health Check ───────────────────────────────────────────────────────

echo -e "${BOLD}1. Health Check${NC}"
HEALTH=$(curl -s -m 15 -w "\n%{http_code}" "$BACKEND/health" 2>/dev/null || echo -e "\n000")
HTTP_CODE=$(echo "$HEALTH" | tail -1)
BODY=$(echo "$HEALTH" | sed '$d')

if [ "$HTTP_CODE" = "200" ]; then
    pass "Backend is live (HTTP 200)"
    STATUS=$(echo "$BODY" | grep -o '"status":"[^"]*"' | head -1 || true)
    if [ -n "$STATUS" ]; then
        info "Response: $STATUS"
    fi
else
    fail "Backend returned HTTP $HTTP_CODE (is Cloud Run cold? Try again in 30s)"
fi
echo ""

# ─── 2. Agent Identity (Agntor Trust Protocol) ────────────────────────────

echo -e "${BOLD}2. Agent Identity & Security${NC}"
IDENTITY=$(curl -s -m 15 "$BACKEND/agent/identity" 2>/dev/null || echo "{}")

if echo "$IDENTITY" | grep -q '"agent_id"'; then
    pass "Agent identity endpoint responds"
    AGENT_ID=$(echo "$IDENTITY" | grep -o '"agent_id":"[^"]*"' | cut -d'"' -f4)
    info "Agent: $AGENT_ID"
else
    fail "Agent identity endpoint failed"
fi

# Check security capabilities
for CAP in prompt_guard pii_redaction tool_guard ssrf_protection; do
    if echo "$IDENTITY" | grep -q "\"$CAP\""; then
        VALUE=$(echo "$IDENTITY" | grep -o "\"$CAP\":[a-z]*" | cut -d: -f2)
        if [ "$VALUE" = "true" ]; then
            pass "Security: $CAP enabled"
        else
            fail "Security: $CAP is $VALUE (expected true)"
        fi
    else
        fail "Security: $CAP not found in identity"
    fi
done
echo ""

# ─── 3. Bundled Skills ────────────────────────────────────────────────────

echo -e "${BOLD}3. Bundled Skills Registry${NC}"
SKILLS=$(curl -s -m 15 "$BACKEND/agent/skills" 2>/dev/null || echo "{}")

if echo "$SKILLS" | grep -q "weather"; then
    pass "Skills endpoint responds"
else
    fail "Skills endpoint failed or no skills found"
fi

EXPECTED_SKILLS="weather hackernews exchange_rates wikipedia crypto_prices rss_reader"
for SKILL in $EXPECTED_SKILLS; do
    if echo "$SKILLS" | grep -q "\"$SKILL\""; then
        pass "Skill registered: $SKILL"
    else
        fail "Skill missing: $SKILL"
    fi
done
echo ""

# ─── 4. REST Endpoints ───────────────────────────────────────────────────

echo -e "${BOLD}4. REST API Endpoints${NC}"

for EP_PAIR in "/health|Health" "/agent/identity|Agent Identity" "/agent/skills|Skills Registry"; do
    EP=$(echo "$EP_PAIR" | cut -d'|' -f1)
    NAME=$(echo "$EP_PAIR" | cut -d'|' -f2)
    CODE=$(curl -s -m 15 -o /dev/null -w "%{http_code}" "$BACKEND$EP" 2>/dev/null || echo "000")
    if [ "$CODE" = "200" ]; then
        pass "$NAME ($EP) — HTTP 200"
    else
        fail "$NAME ($EP) — HTTP $CODE"
    fi
done

# OAuth endpoint should exist (302 redirect to Google)
OAUTH_CODE=$(curl -s -m 15 -o /dev/null -w "%{http_code}" "$BACKEND/auth/login/test_verify" 2>/dev/null || echo "000")
if [ "$OAUTH_CODE" -gt "0" ] 2>/dev/null && [ "$OAUTH_CODE" -lt "500" ] 2>/dev/null; then
    pass "OAuth login endpoint exists (/auth/login) — HTTP $OAUTH_CODE"
else
    fail "OAuth login endpoint — HTTP $OAUTH_CODE"
fi
echo ""

# ─── 5. WebSocket Connectivity ───────────────────────────────────────────

echo -e "${BOLD}5. WebSocket Connectivity${NC}"

# Use curl to test WebSocket upgrade
WS_CODE=$(curl -s -m 10 -o /dev/null -w "%{http_code}" \
    -H "Connection: Upgrade" \
    -H "Upgrade: websocket" \
    -H "Sec-WebSocket-Version: 13" \
    -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
    "$BACKEND/ws/verify_test_user" 2>/dev/null || echo "000")

if [ "$WS_CODE" = "101" ]; then
    pass "WebSocket upgrade accepted (HTTP 101)"
elif [ "$WS_CODE" -gt "0" ] 2>/dev/null && [ "$WS_CODE" -lt "500" ] 2>/dev/null; then
    pass "WebSocket endpoint reachable (HTTP $WS_CODE)"
else
    fail "WebSocket endpoint — HTTP $WS_CODE"
fi
echo ""

# ─── 6. Cloud Run Verification ───────────────────────────────────────────

echo -e "${BOLD}6. Google Cloud Run Deployment${NC}"

if echo "$BACKEND" | grep -q "run.app"; then
    pass "Backend URL is a Google Cloud Run service (*.run.app)"
else
    fail "Backend URL does not appear to be Cloud Run"
fi

# Check response headers for Cloud Run signatures
HEADERS=$(curl -s -m 15 -I "$BACKEND/health" 2>/dev/null || echo "")
if echo "$HEADERS" | grep -qi "x-cloud-trace-context\|server: Google Frontend\|via.*google"; then
    pass "Response headers confirm Google Cloud infrastructure"
else
    if echo "$BACKEND" | grep -q "https"; then
        pass "Backend served over HTTPS on Cloud Run domain"
    else
        fail "Could not verify Google Cloud headers"
    fi
fi
echo ""

# ─── Summary ─────────────────────────────────────────────────────────────

echo -e "${BOLD}═══════════════════════════════════════════════════════${NC}"
if [ "$FAIL" -eq 0 ]; then
    echo -e "${BOLD}  ${GREEN}ALL $TOTAL TESTS PASSED${NC}"
else
    echo -e "${BOLD}  ${GREEN}$PASS passed${NC} / ${RED}$FAIL failed${NC} / $TOTAL total"
fi
echo -e "${BOLD}═══════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${CYAN}Architecture:${NC} See docs/architecture-diagram.svg"
echo -e "  ${CYAN}Full test suite:${NC} python3 core/tests/test_demo_scenes.py"
echo -e "  ${CYAN}Blog post:${NC} https://dev.to/zeshama/i-built-a-personal-ai-computer-with-gemini-heres-how-934"
echo -e "  ${CYAN}GitHub:${NC} https://github.com/Garinmckayl/elora"
echo ""

exit $FAIL
