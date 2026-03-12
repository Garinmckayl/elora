"""
Agntor Security Layer for Elora
================================
Agent identity, prompt injection guard, PII redaction, tool guardrails,
and SSRF protection. Powered by the Agntor trust protocol (@agntor/sdk).

This module implements the core Agntor security primitives natively in Python
for the Elora backend. For the full SDK with escrow/settlement/reputation,
see: https://github.com/agntor/agntor

Security layers applied to every agent interaction:
1. Input Guard    -- prompt injection detection (regex + heuristic)
2. PII Redaction  -- strip sensitive data before processing
3. Tool Guard     -- policy-based allow/blocklist for tool execution
4. SSRF Guard     -- validate URLs before fetching
5. Output Redact  -- strip any leaked secrets from responses
"""

import re
import os
import logging
import ipaddress
import socket
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger("elora.agntor")

# ---------------------------------------------------------------------------
# Agent Identity
# ---------------------------------------------------------------------------

AGENT_ID = os.getenv("AGNTOR_AGENT_ID", "agent://elora")
AGENT_VERSION = os.getenv("ELORA_VERSION", "1.0.0")


def get_agent_identity() -> dict:
    """Return Elora's agent identity in Agntor protocol format."""
    return {
        "agent_id": AGENT_ID,
        "version": AGENT_VERSION,
        "capabilities": [
            "text_chat", "voice_chat", "code_execution", "skill_system",
            "memory", "proactive_awareness", "vision", "browser_automation",
            "email", "calendar", "file_management", "image_generation",
            "music_generation", "face_recognition",
        ],
        "security": {
            "prompt_guard": True,
            "pii_redaction": True,
            "tool_guard": True,
            "ssrf_protection": True,
            "sandbox_isolation": "e2b",
        },
        "trust_protocol": "agntor/v1",
    }


# ---------------------------------------------------------------------------
# Prompt Injection Guard
# ---------------------------------------------------------------------------

# Fast regex patterns for known injection techniques
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)", re.I),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|above)", re.I),
    re.compile(r"you\s+are\s+now\s+(a|an|the)\s+", re.I),
    re.compile(r"forget\s+(everything|all|your)\s+(you|instructions?|rules?)", re.I),
    re.compile(r"new\s+instructions?:\s*", re.I),
    re.compile(r"system\s*prompt\s*:", re.I),
    re.compile(r"\[system\]", re.I),
    re.compile(r"<\s*system\s*>", re.I),
    re.compile(r"jailbreak", re.I),
    re.compile(r"DAN\s+mode", re.I),
    re.compile(r"pretend\s+you\s+(are|have)\s+no\s+(restrictions?|rules?|limits?)", re.I),
    re.compile(r"reveal\s+(your|the)\s+(system|initial)\s+(prompt|instructions?)", re.I),
    re.compile(r"what\s+(are|is)\s+your\s+(system|initial)\s+(prompt|instructions?)", re.I),
]

# Heuristic checks
INJECTION_HEURISTICS = {
    "excessive_role_play": re.compile(r"(act\s+as|roleplay\s+as|you\s+are\s+now)\s+.{3,}", re.I),
    "delimiter_injection": re.compile(r"(---+|===+|\*\*\*+|```)\s*(system|admin|root)", re.I),
    "encoding_obfuscation": re.compile(r"(base64|rot13|hex)\s*(encode|decode)", re.I),
}


def guard_input(text: str) -> dict:
    """
    Check user input for prompt injection attacks.
    Three-layer approach: regex patterns, heuristic analysis, risk scoring.

    Returns:
        dict: {classification: 'pass'|'warn'|'block', risk_score: float, violations: list}
    """
    violations = []
    risk_score = 0.0

    # Layer 1: Fast regex patterns
    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            violations.append({
                "type": "injection_pattern",
                "detail": pattern.pattern[:80],
            })
            risk_score += 0.4

    # Layer 2: Heuristic analysis
    for name, pattern in INJECTION_HEURISTICS.items():
        if pattern.search(text):
            violations.append({
                "type": "heuristic",
                "detail": name,
            })
            risk_score += 0.2

    # Layer 3: Structural analysis
    # Check for suspicious length (extremely long inputs often contain injections)
    if len(text) > 5000:
        risk_score += 0.1
    # Check for high ratio of special characters
    special_ratio = sum(1 for c in text if not c.isalnum() and not c.isspace()) / max(len(text), 1)
    if special_ratio > 0.3:
        risk_score += 0.1

    risk_score = min(risk_score, 1.0)

    if risk_score >= 0.6:
        classification = "block"
    elif risk_score >= 0.3:
        classification = "warn"
    else:
        classification = "pass"

    if violations:
        logger.warning(f"[Agntor Guard] {classification}: score={risk_score:.2f} violations={len(violations)}")

    return {
        "classification": classification,
        "risk_score": round(risk_score, 3),
        "violations": violations,
    }


# ---------------------------------------------------------------------------
# PII & Secret Redaction
# ---------------------------------------------------------------------------

PII_PATTERNS = {
    "EMAIL": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    "PHONE": re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "CREDIT_CARD": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
    "IP_ADDRESS": re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
}

SECRET_PATTERNS = {
    "AWS_ACCESS_KEY": re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),
    "AWS_SECRET_KEY": re.compile(r"(?i)(aws[_-]?secret[_-]?access[_-]?key\s*[=:]\s*)[A-Za-z0-9/+=]{40}"),
    "BEARER_TOKEN": re.compile(r"\b(Bearer\s+[A-Za-z0-9\-._~+/]+=*)\b"),
    "API_KEY_GENERIC": re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)[A-Za-z0-9\-._]{20,}"),
    "PRIVATE_KEY_HEX": re.compile(r"\b(0x[a-fA-F0-9]{64})\b"),
    "GOOGLE_API_KEY": re.compile(r"\b(AIza[0-9A-Za-z\-_]{35})\b"),
    "JWT_TOKEN": re.compile(r"\b(eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+)\b"),
}


def redact(text: str, redact_pii: bool = True, redact_secrets: bool = True) -> dict:
    """
    Strip sensitive data from text. Returns the redacted text and findings.

    Args:
        text: Input text to scan.
        redact_pii: Whether to redact PII (email, phone, SSN, etc.).
        redact_secrets: Whether to redact secrets (API keys, tokens, etc.).

    Returns:
        dict: {redacted: str, findings: list, count: int}
    """
    findings = []
    redacted = text

    patterns = {}
    if redact_pii:
        patterns.update(PII_PATTERNS)
    if redact_secrets:
        patterns.update(SECRET_PATTERNS)

    for label, pattern in patterns.items():
        matches = pattern.findall(redacted)
        for match in matches:
            match_str = match if isinstance(match, str) else match[0] if match else ""
            if match_str and len(match_str) > 3:
                findings.append({"type": label, "preview": match_str[:8] + "..."})
                redacted = redacted.replace(match_str, f"[{label}]")

    if findings:
        logger.info(f"[Agntor Redact] Stripped {len(findings)} sensitive item(s)")

    return {
        "redacted": redacted,
        "findings": findings,
        "count": len(findings),
    }


# ---------------------------------------------------------------------------
# Tool Guard
# ---------------------------------------------------------------------------

# Tools that are always blocked (never allow agent to call these)
TOOL_BLOCKLIST = {
    "shell.exec",        # Direct shell execution
    "os.system",         # OS-level system calls
    "eval",              # Arbitrary eval
    "subprocess.run",    # Direct subprocess
}

# Tools that require explicit user confirmation
TOOL_CONFIRM_LIST = {
    "send_email",        # Sending emails
    "send_sms",          # Sending SMS
    "delete_file",       # Deleting files
    "batch_manage_emails",  # Bulk email operations
    "delete_calendar_event",  # Deleting events
    "publish_skill",     # Publishing to community
}


def guard_tool(tool_name: str, tool_input: Optional[dict] = None) -> dict:
    """
    Check if a tool invocation is allowed under the current security policy.

    Returns:
        dict: {allowed: bool, requires_confirmation: bool, reason: str}
    """
    if tool_name in TOOL_BLOCKLIST:
        logger.warning(f"[Agntor ToolGuard] BLOCKED: {tool_name}")
        return {
            "allowed": False,
            "requires_confirmation": False,
            "reason": f"Tool '{tool_name}' is blocked by security policy.",
        }

    requires_confirmation = tool_name in TOOL_CONFIRM_LIST

    return {
        "allowed": True,
        "requires_confirmation": requires_confirmation,
        "reason": "ok" if not requires_confirmation else f"Tool '{tool_name}' requires user confirmation.",
    }


# ---------------------------------------------------------------------------
# SSRF Protection
# ---------------------------------------------------------------------------

BLOCKED_SCHEMES = {"file", "ftp", "gopher", "data", "javascript"}

PRIVATE_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def validate_url(url: str) -> dict:
    """
    Validate a URL against SSRF attacks. Checks scheme, resolves DNS,
    and verifies the IP isn't in a private/internal range.

    Returns:
        dict: {safe: bool, reason: str}
    """
    try:
        parsed = urlparse(url)

        # Check scheme
        if parsed.scheme.lower() in BLOCKED_SCHEMES:
            return {"safe": False, "reason": f"Blocked scheme: {parsed.scheme}"}

        if not parsed.hostname:
            return {"safe": False, "reason": "No hostname in URL"}

        # Resolve DNS and check IP
        try:
            resolved = socket.getaddrinfo(parsed.hostname, None)
            for _, _, _, _, addr in resolved:
                ip = ipaddress.ip_address(addr[0])
                for network in PRIVATE_RANGES:
                    if ip in network:
                        return {"safe": False, "reason": f"URL resolves to private IP: {ip}"}
        except socket.gaierror:
            return {"safe": False, "reason": f"DNS resolution failed for {parsed.hostname}"}

        return {"safe": True, "reason": "ok"}

    except Exception as e:
        return {"safe": False, "reason": f"URL validation error: {str(e)}"}


# ---------------------------------------------------------------------------
# Composite security check -- run all guards on a message
# ---------------------------------------------------------------------------

def secure_message(text: str, tool_name: Optional[str] = None) -> dict:
    """
    Run the full Agntor security pipeline on an incoming message/tool call.
    Used as middleware before processing any user input.

    Returns:
        dict: {
            allowed: bool,
            sanitized_text: str,
            guard_result: dict,
            redaction_result: dict,
            tool_guard_result: dict | None,
        }
    """
    # 1. Guard input for injection
    guard_result = guard_input(text)

    # 2. Redact PII/secrets from input
    redaction_result = redact(text)
    sanitized = redaction_result["redacted"]

    # 3. Tool guard (if applicable)
    tool_result = None
    if tool_name:
        tool_result = guard_tool(tool_name)

    # Determine if we should proceed
    allowed = True
    if guard_result["classification"] == "block":
        allowed = False
    if tool_result and not tool_result["allowed"]:
        allowed = False

    return {
        "allowed": allowed,
        "sanitized_text": sanitized,
        "guard_result": guard_result,
        "redaction_result": redaction_result,
        "tool_guard_result": tool_result,
    }
