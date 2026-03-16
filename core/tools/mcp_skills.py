"""
Elora Skill System -- OpenClaw-inspired, consumer-grade.

Skills are modular capabilities that Elora can discover, install, create, and execute.
Each skill is a definition (name, description, code template) stored per-user in Firestore
and executed in the user's personal E2B sandbox.

Three skill sources (highest to lowest precedence):
1. User skills    -- created/installed by the user, stored in Firestore per-user
2. Community      -- curated registry in Firestore `skill_registry/` collection
3. Bundled        -- shipped with Elora (hardcoded defaults)

Elora can also CREATE new skills on the fly -- generating the code herself
and saving it for future use. This is the "personal AGI" differentiator.
"""

import os
import json
import time
import logging
from typing import Optional

import httpx

logger = logging.getLogger("elora.skills")

E2B_API_KEY = os.getenv("E2B_API_KEY", "")

# ClawHub -- OpenClaw community skill registry
CLAWHUB_API = "https://clawhub.ai/api/v1"
CLAWHUB_TIMEOUT = 8  # seconds

# In-memory skill store (fallback when Firestore is unavailable)
_mem_skills: dict[str, dict] = {}  # user_id -> {skill_name -> skill_def}


def _get_firestore():
    """Lazy Firestore client."""
    from google.cloud import firestore
    return firestore.Client()


# ---------------------------------------------------------------------------
# Bundled skills -- ship with Elora, always available
# ---------------------------------------------------------------------------

BUNDLED_SKILLS = {
    "weather": {
        "name": "weather",
        "description": "Get current weather and forecasts for any location. Uses Open-Meteo (free, no API key).",
        "category": "utility",
        "code_template": """
import requests, json

def get_weather(location: str):
    # Geocode location
    geo = requests.get(f"https://geocoding-api.open-meteo.com/v1/search?name={location}&count=1").json()
    if not geo.get("results"):
        return {"error": f"Location '{location}' not found"}
    lat, lon = geo["results"][0]["latitude"], geo["results"][0]["longitude"]
    name = geo["results"][0].get("name", location)
    
    # Get weather
    resp = requests.get(
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=auto"
    ).json()
    
    current = resp.get("current", {})
    daily = resp.get("daily", {})
    return {
        "location": name,
        "temperature": current.get("temperature_2m"),
        "humidity": current.get("relative_humidity_2m"),
        "wind_speed": current.get("wind_speed_10m"),
        "daily_high": daily.get("temperature_2m_max", [None])[0],
        "daily_low": daily.get("temperature_2m_min", [None])[0],
    }

result = get_weather("{location}")
print(json.dumps(result))
""",
        "parameters": {"location": "City name or place"},
    },
    "hackernews": {
        "name": "hackernews",
        "description": "Get top stories from Hacker News with titles, scores, and URLs.",
        "category": "news",
        "code_template": """
import requests, json

def get_hn_top(count=10):
    ids = requests.get("https://hacker-news.firebaseio.com/v0/topstories.json").json()[:count]
    stories = []
    for sid in ids:
        s = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json").json()
        stories.append({"title": s.get("title"), "url": s.get("url", ""), "score": s.get("score", 0), "by": s.get("by", "")})
    return stories

result = get_hn_top({count})
print(json.dumps(result))
""",
        "parameters": {"count": "Number of stories (default 10)"},
    },
    "exchange_rates": {
        "name": "exchange_rates",
        "description": "Get current currency exchange rates. Converts between any currencies.",
        "category": "finance",
        "code_template": """
import requests, json

def get_rates(base="USD"):
    resp = requests.get(f"https://api.exchangerate-api.com/v4/latest/{base}").json()
    return {"base": base, "rates": resp.get("rates", {}), "updated": resp.get("date")}

result = get_rates("{base_currency}")
print(json.dumps(result))
""",
        "parameters": {"base_currency": "Base currency code (e.g. USD, EUR, GBP)"},
    },
    "wikipedia": {
        "name": "wikipedia",
        "description": "Search Wikipedia and get article summaries.",
        "category": "knowledge",
        "code_template": """
import requests, json

def wiki_summary(query):
    resp = requests.get("https://en.wikipedia.org/api/rest_v1/page/summary/" + query.replace(" ", "_")).json()
    if "title" in resp:
        return {"title": resp["title"], "summary": resp.get("extract", ""), "url": resp.get("content_urls", {}).get("desktop", {}).get("page", "")}
    # Fallback: search
    search = requests.get(f"https://en.wikipedia.org/w/api.php?action=opensearch&search={query}&limit=5&format=json").json()
    return {"results": search[1] if len(search) > 1 else [], "urls": search[3] if len(search) > 3 else []}

result = wiki_summary("{query}")
print(json.dumps(result))
""",
        "parameters": {"query": "Search term or article title"},
    },
    "crypto_prices": {
        "name": "crypto_prices",
        "description": "Get current cryptocurrency prices from CoinGecko (free, no API key).",
        "category": "finance",
        "code_template": """
import requests, json

def get_crypto(coins="bitcoin,ethereum", currency="usd"):
    resp = requests.get(
        f"https://api.coingecko.com/api/v3/simple/price?ids={coins}&vs_currencies={currency}&include_24hr_change=true"
    ).json()
    return resp

result = get_crypto("{coins}", "{currency}")
print(json.dumps(result))
""",
        "parameters": {"coins": "Comma-separated coin IDs (e.g. bitcoin,ethereum)", "currency": "Target currency (e.g. usd)"},
    },
    "rss_reader": {
        "name": "rss_reader",
        "description": "Read and parse any RSS/Atom feed. Great for news, blogs, podcasts.",
        "category": "utility",
        "code_template": """
import feedparser, json

def read_feed(url, count=10):
    feed = feedparser.parse(url)
    entries = []
    for e in feed.entries[:count]:
        entries.append({
            "title": e.get("title", ""),
            "link": e.get("link", ""),
            "published": e.get("published", ""),
            "summary": e.get("summary", "")[:300],
        })
    return {"feed_title": feed.feed.get("title", ""), "entries": entries}

result = read_feed("{feed_url}", {count})
print(json.dumps(result))
""",
        "parameters": {"feed_url": "URL of the RSS/Atom feed", "count": "Number of entries (default 10)"},
    },
    "ethio_power": {
        "name": "ethio_power",
        "description": "Ethiopian power outage estimator. Calculates remaining battery work time and suggests when to save work, based on average Addis Ababa load-shedding patterns.",
        "category": "utility",
        "code_template": """
import json
from datetime import datetime, timedelta

def check_power_schedule(battery_percent=100, work_type="coding"):
    # Average Addis Ababa load-shedding: 2-4 hour blocks, typically 1-2 outages per day
    # Peak outage hours: 6-8 AM, 12-2 PM, 6-8 PM (based on EEU patterns)
    now = datetime.utcnow() + timedelta(hours=3)  # UTC+3 for EAT
    hour = now.hour

    # Estimate battery life based on work type
    drain_rates = {"coding": 15, "browsing": 12, "video_call": 25, "idle": 5}  # %/hour
    drain = drain_rates.get(work_type, 15)
    hours_left = max(0, (battery_percent - 5) / drain)  # Keep 5% reserve

    # Predict next likely outage window
    outage_windows = [(6, 8), (12, 14), (18, 20)]
    next_outage = None
    for start, end in outage_windows:
        if hour < start:
            next_outage = {"start": f"{start}:00", "end": f"{end}:00", "hours_until": start - hour}
            break
    if not next_outage:
        next_outage = {"start": "06:00", "end": "08:00", "hours_until": 24 - hour + 6, "note": "Tomorrow morning"}

    # Recommendations
    recommendations = []
    if hours_left < 2:
        recommendations.append("URGENT: Save all work NOW. Battery critically low.")
        recommendations.append("Push your code to GitHub before power dies.")
    elif hours_left < next_outage.get("hours_until", 99):
        recommendations.append(f"You have ~{hours_left:.1f}h of battery. Next outage likely at {next_outage['start']}.")
        recommendations.append("Consider saving work and charging if power is available.")
    else:
        recommendations.append(f"You're good. ~{hours_left:.1f}h battery, next outage not until {next_outage['start']}.")

    if work_type == "coding":
        recommendations.append("Tip: Use 'git stash' before stepping away. Auto-save everything.")

    return {
        "current_time": now.strftime("%H:%M EAT"),
        "battery_hours_remaining": round(hours_left, 1),
        "work_type": work_type,
        "next_likely_outage": next_outage,
        "recommendations": recommendations,
        "status": "critical" if hours_left < 1 else "warning" if hours_left < 2 else "ok",
    }

result = check_power_schedule({battery_percent}, "{work_type}")
print(json.dumps(result))
""",
        "parameters": {"battery_percent": "Current battery percentage (0-100)", "work_type": "What you're doing: coding, browsing, video_call, idle"},
    },
}


# ---------------------------------------------------------------------------
# Skill registry operations
# ---------------------------------------------------------------------------

def search_skills(query: str, user_id: str) -> dict:
    """
    Search for skills in the community registry and bundled skills.
    Elora uses this to find capabilities she doesn't have yet.

    Args:
        query: What the user needs (e.g. "track crypto prices", "read RSS feeds").

    Returns:
        dict: Matching skills from bundled + community registry.
    """
    query_lower = query.lower()
    results = []

    # Search bundled skills
    for name, skill in BUNDLED_SKILLS.items():
        if (query_lower in skill["description"].lower() or
                query_lower in name.lower() or
                query_lower in skill.get("category", "").lower()):
            results.append({
                "name": name,
                "description": skill["description"],
                "category": skill.get("category", "general"),
                "source": "bundled",
                "installed": False,
            })

    # Search community registry in Firestore
    try:
        db = _get_firestore()
        registry = db.collection("skill_registry").stream()
        for doc in registry:
            skill = doc.to_dict()
            skill_name = skill.get("name", doc.id)
            skill_desc = skill.get("description", "")
            skill_cat = skill.get("category", "")
            if (query_lower in skill_desc.lower() or
                    query_lower in skill_name.lower() or
                    query_lower in skill_cat.lower()):
                results.append({
                    "name": skill_name,
                    "description": skill_desc,
                    "category": skill_cat,
                    "source": "community",
                    "author": skill.get("author", "community"),
                    "installed": False,
                })
    except Exception as e:
        logger.warning(f"[Skills] Registry search failed: {e}")

    # Search ClawHub (OpenClaw community skill hub)
    try:
        resp = httpx.get(
            f"{CLAWHUB_API}/skills",
            params={"limit": 20},
            timeout=CLAWHUB_TIMEOUT,
        )
        if resp.status_code == 200:
            clawhub_items = resp.json().get("items", [])
            for item in clawhub_items:
                slug = item.get("slug", "")
                display = item.get("displayName", slug)
                summary = item.get("summary", "")
                stats = item.get("stats", {})
                # Match against query
                if (query_lower in summary.lower() or
                        query_lower in display.lower() or
                        query_lower in slug.lower()):
                    results.append({
                        "name": slug,
                        "description": f"{display}: {summary[:200]}",
                        "category": "clawhub",
                        "source": "clawhub",
                        "author": slug,
                        "downloads": stats.get("downloads", 0),
                        "stars": stats.get("stars", 0),
                        "url": f"https://clawhub.ai/{slug}",
                        "installed": False,
                    })
    except Exception as e:
        logger.warning(f"[Skills] ClawHub search failed: {e}")

    # Check which are already installed by this user
    try:
        db = _get_firestore()
        user_skills = db.collection("users").document(user_id).collection("skills").stream()
        installed_names = {doc.id for doc in user_skills}
        for r in results:
            if r["name"] in installed_names:
                r["installed"] = True
    except Exception:
        pass

    if not results:
        return {
            "status": "success",
            "skills": [],
            "report": (
                f"No skills found matching '{query}'. But I can create a custom skill for this! "
                "Just tell me what you need and I'll write it."
            ),
        }

    return {
        "status": "success",
        "skills": results,
        "report": f"Found {len(results)} skill(s) matching '{query}'.",
    }


def install_skill(skill_name: str, user_id: str) -> dict:
    """
    Install a skill for the user. Copies the skill definition to the user's profile
    and deploys the code to their sandbox.

    Args:
        skill_name: Name of the skill to install (from search results or bundled).

    Returns:
        dict: Installation status.
    """
    # Find the skill definition
    skill_def = None

    # Check bundled first
    if skill_name in BUNDLED_SKILLS:
        skill_def = BUNDLED_SKILLS[skill_name].copy()
        skill_def["source"] = "bundled"

    # Check community registry
    if not skill_def:
        try:
            db = _get_firestore()
            doc = db.collection("skill_registry").document(skill_name).get()
            if doc.exists:
                skill_def = doc.to_dict()
                skill_def["source"] = "community"
        except Exception as e:
            logger.warning(f"[Skills] Registry lookup failed: {e}")

    # Check ClawHub (OpenClaw community hub)
    if not skill_def:
        try:
            resp = httpx.get(
                f"{CLAWHUB_API}/skills",
                params={"q": skill_name, "limit": 5},
                timeout=CLAWHUB_TIMEOUT,
            )
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                for item in items:
                    slug = item.get("slug", "")
                    if slug.lower() == skill_name.lower() or skill_name.lower() in slug.lower():
                        # Convert OpenClaw SKILL.md format to Elora skill definition
                        readme = item.get("readme", "")
                        display = item.get("displayName", slug)
                        summary = item.get("summary", "")

                        # Extract code from readme if present (between ```python blocks)
                        code_template = ""
                        if "```python" in readme:
                            parts = readme.split("```python")
                            if len(parts) > 1:
                                code_block = parts[1].split("```")[0].strip()
                                code_template = code_block

                        # If no code found, create a stub that describes the skill
                        if not code_template:
                            code_template = (
                                f"# ClawHub Skill: {display}\n"
                                f"# {summary}\n"
                                f"# Source: https://clawhub.ai/{slug}\n\n"
                                f"import json\n"
                                f"print(json.dumps({{'skill': '{slug}', 'status': 'loaded', "
                                f"'description': '{summary[:200]}'}})"
                                f")\n"
                            )

                        skill_def = {
                            "name": slug,
                            "description": f"{display}: {summary}",
                            "category": "clawhub",
                            "code_template": code_template,
                            "parameters": {},
                            "source": "clawhub",
                        }
                        break
        except Exception as e:
            logger.warning(f"[Skills] ClawHub install lookup failed: {e}")

    if not skill_def:
        return {
            "status": "error",
            "report": f"Skill '{skill_name}' not found in bundled skills, community registry, or ClawHub.",
        }

    # Save to user's skills collection
    skill_record = {
        "name": skill_def["name"],
        "description": skill_def["description"],
        "category": skill_def.get("category", "general"),
        "code_template": skill_def.get("code_template", ""),
        "parameters": skill_def.get("parameters", {}),
        "source": skill_def.get("source", "unknown"),
        "installed_at": time.time(),
        "enabled": True,
    }
    try:
        db = _get_firestore()
        db.collection("users").document(user_id).collection("skills").document(skill_name).set(skill_record)
    except Exception as e:
        logger.warning(f"[Skills] Firestore save failed, using in-memory: {e}")
        _mem_skills.setdefault(user_id, {})[skill_name] = skill_record

    # Deploy code to user's sandbox
    try:
        from tools.e2b_sandbox import write_sandbox_file
        code = skill_def.get("code_template", "")
        if code:
            write_sandbox_file(user_id, f"/home/user/skills/{skill_name}.py", code)
    except Exception as e:
        logger.warning(f"[Skills] Failed to deploy to sandbox: {e}")

    return {
        "status": "success",
        "report": (
            f"Skill '{skill_name}' installed! {skill_def['description']} "
            f"I can now use this skill whenever you need it."
        ),
    }


def create_skill(
    name: str,
    description: str,
    code: str,
    parameters: str,
    user_id: str,
    category: str = "custom",
) -> dict:
    """
    Create a brand new skill from scratch. This is Elora's superpower -- she can write
    new capabilities and save them for future use. The code runs in the user's sandbox.

    Args:
        name: Unique skill name (lowercase, no spaces, use underscores).
        description: What this skill does (human-readable).
        code: Python code that implements the skill. Should print JSON output.
        parameters: JSON string describing the parameters the skill accepts.
        category: Category tag (e.g. 'utility', 'finance', 'automation').

    Returns:
        dict: Creation status.
    """
    # Parse parameters
    try:
        params = json.loads(parameters) if isinstance(parameters, str) else parameters
    except json.JSONDecodeError:
        params = {"input": parameters}

    # Validate the code by running it in the sandbox first (dry run)
    try:
        from tools.e2b_sandbox import run_in_sandbox
        test_result = run_in_sandbox(user_id, code, "python", timeout=30)
        if test_result.get("status") == "error" and test_result.get("error"):
            return {
                "status": "error",
                "report": (
                    f"Skill code has an error: {test_result['error'][:300]}. "
                    "Fix the code and try again."
                ),
            }
    except Exception as e:
        logger.warning(f"[Skills] Dry run failed: {e}")

    # Save to user's skills
    try:
        db = _get_firestore()
        db.collection("users").document(user_id).collection("skills").document(name).set({
            "name": name,
            "description": description,
            "category": category,
            "code_template": code,
            "parameters": params,
            "source": "user_created",
            "created_at": time.time(),
            "enabled": True,
        })
    except Exception as e:
        return {"status": "error", "report": f"Failed to save skill: {e}"}

    # Deploy to sandbox
    try:
        from tools.e2b_sandbox import write_sandbox_file
        write_sandbox_file(user_id, f"/home/user/skills/{name}.py", code)
    except Exception:
        pass

    # Also publish to community registry if it looks useful
    # (could add a flag for this, for now user-created stays private)

    return {
        "status": "success",
        "report": (
            f"Skill '{name}' created and saved! {description} "
            f"I'll use this automatically whenever it's relevant. "
            f"It's saved in your personal skill library."
        ),
    }


def execute_skill(
    skill_name: str,
    parameters: str,
    user_id: str,
) -> dict:
    """
    Execute an installed skill with the given parameters.
    Runs in the user's personal sandbox.

    Args:
        skill_name: Name of the skill to execute.
        parameters: JSON string of parameter values to fill into the skill template.

    Returns:
        dict: Execution results.
    """
    # Load skill definition
    skill_def = None

    # Check user's installed skills first
    try:
        db = _get_firestore()
        doc = db.collection("users").document(user_id).collection("skills").document(skill_name).get()
        if doc.exists:
            skill_def = doc.to_dict()
    except Exception:
        pass

    # Check in-memory skill store (fallback)
    if not skill_def and user_id in _mem_skills and skill_name in _mem_skills[user_id]:
        skill_def = _mem_skills[user_id][skill_name]

    # Fall back to bundled
    if not skill_def and skill_name in BUNDLED_SKILLS:
        skill_def = BUNDLED_SKILLS[skill_name]

    if not skill_def:
        return {
            "status": "error",
            "report": (
                f"Skill '{skill_name}' is not installed. "
                f"Use search_skills to find it, or create_skill to build a new one."
            ),
        }

    # Parse parameters and fill template
    try:
        params = json.loads(parameters) if isinstance(parameters, str) else parameters
    except json.JSONDecodeError:
        params = {}

    code = skill_def.get("code_template", "")
    for key, value in params.items():
        code = code.replace("{" + key + "}", str(value))

    # Execute in user's sandbox
    try:
        from tools.e2b_sandbox import run_in_sandbox
        result = run_in_sandbox(user_id, code, "python", timeout=60)

        if result.get("status") == "success":
            output = result.get("stdout", "") or "\n".join(result.get("results", []))
            return {
                "status": "success",
                "skill": skill_name,
                "output": output,
                "report": f"Skill '{skill_name}' executed successfully.",
            }
        else:
            return {
                "status": "error",
                "skill": skill_name,
                "error": result.get("error", result.get("stderr", "")),
                "report": f"Skill '{skill_name}' failed: {result.get('error', '')[:200]}",
            }
    except Exception as e:
        return {
            "status": "error",
            "report": f"Execution failed: {str(e)[:200]}",
        }


def run_code_in_sandbox(
    code: str,
    user_id: str,
    language: str = "python",
    timeout: int = 30,
) -> dict:
    """
    Execute arbitrary code in the user's personal sandbox.
    The sandbox is persistent -- installed packages and files survive across calls.

    Args:
        code: Python or JavaScript code to execute.
        language: 'python' or 'javascript'.
        timeout: Max execution time in seconds (5-120).

    Returns:
        dict: Execution results with stdout, stderr, and any errors.
    """
    try:
        from tools.e2b_sandbox import run_in_sandbox
        result = run_in_sandbox(user_id, code, language, min(max(timeout, 5), 120))

        if result.get("status") == "success":
            output = result.get("stdout", "") or "\n".join(result.get("results", []))
            return {
                "status": "success",
                "output": output,
                "report": "Code executed successfully in your personal sandbox.",
            }
        else:
            return {
                "status": "error",
                "error": result.get("error", result.get("stderr", "")),
                "stdout": result.get("stdout", ""),
                "report": f"Code execution failed: {result.get('error', '')[:200]}",
            }
    except Exception as e:
        return {"status": "error", "report": f"Sandbox error: {str(e)[:200]}"}


def list_installed_skills(user_id: str) -> dict:
    """
    List all skills installed by the user (user-created + installed from registry).

    Returns:
        dict: List of installed skills with their descriptions and status.
    """
    skills = []

    # Get user's installed skills from Firestore
    try:
        db = _get_firestore()
        docs = db.collection("users").document(user_id).collection("skills").stream()
        for doc in docs:
            data = doc.to_dict()
            skills.append({
                "name": doc.id,
                "description": data.get("description", ""),
                "category": data.get("category", "general"),
                "source": data.get("source", "unknown"),
                "enabled": data.get("enabled", True),
                "created_at": data.get("created_at") or data.get("installed_at"),
            })
    except Exception as e:
        logger.warning(f"[Skills] Failed to list user skills from Firestore: {e}")

    # Include in-memory skills (fallback store)
    for sname, sdef in _mem_skills.get(user_id, {}).items():
        if sname not in {s["name"] for s in skills}:
            skills.append({
                "name": sname,
                "description": sdef.get("description", ""),
                "category": sdef.get("category", "general"),
                "source": sdef.get("source", "unknown"),
                "enabled": sdef.get("enabled", True),
                "created_at": sdef.get("installed_at"),
            })

    # Also list available bundled skills
    bundled = []
    installed_names = {s["name"] for s in skills}
    for name, skill in BUNDLED_SKILLS.items():
        bundled.append({
            "name": name,
            "description": skill["description"],
            "category": skill.get("category", "general"),
            "source": "bundled",
            "installed": name in installed_names,
        })

    report_parts = []
    if skills:
        report_parts.append(f"{len(skills)} installed skill(s)")
    report_parts.append(f"{len(bundled)} bundled skill(s) available")

    return {
        "status": "success",
        "installed_skills": skills,
        "bundled_skills": bundled,
        "report": f"Skills: {', '.join(report_parts)}.",
    }


def remove_skill(skill_name: str, user_id: str) -> dict:
    """
    Remove/uninstall a skill from the user's profile.

    Args:
        skill_name: Name of the skill to remove.

    Returns:
        dict: Removal status.
    """
    try:
        db = _get_firestore()
        doc_ref = db.collection("users").document(user_id).collection("skills").document(skill_name)
        doc = doc_ref.get()
        if not doc.exists:
            return {"status": "error", "report": f"Skill '{skill_name}' is not installed."}
        doc_ref.delete()
    except Exception as e:
        return {"status": "error", "report": f"Failed to remove skill: {e}"}

    return {
        "status": "success",
        "report": f"Skill '{skill_name}' has been removed from your skill library.",
    }


def install_sandbox_package(package: str, user_id: str, language: str = "python") -> dict:
    """
    Install a package in the user's personal sandbox. The package persists
    across conversations -- once installed, it's always available.

    Args:
        package: Package name to install (e.g. 'pandas', 'numpy', 'openai').
        language: 'python' (pip) or 'javascript' (npm).

    Returns:
        dict: Installation status.
    """
    try:
        from tools.e2b_sandbox import install_package
        result = install_package(user_id, package, language)

        if result.get("status") == "success":
            output = result.get("stdout", "")
            return {
                "status": "success",
                "report": f"Package '{package}' installed in your sandbox. It's now available for all future code execution and skills.",
            }
        else:
            return {
                "status": "error",
                "error": result.get("error", result.get("stderr", "")),
                "report": f"Failed to install '{package}': {result.get('error', '')[:200]}",
            }
    except Exception as e:
        return {"status": "error", "report": f"Package installation failed: {str(e)[:200]}"}


def publish_skill(skill_name: str, user_id: str) -> dict:
    """
    Publish a user-created skill to the community registry so other Elora users can discover it.

    Args:
        skill_name: Name of the skill to publish.

    Returns:
        dict: Publication status.
    """
    # Load from user's skills
    try:
        db = _get_firestore()
        doc = db.collection("users").document(user_id).collection("skills").document(skill_name).get()
        if not doc.exists:
            return {"status": "error", "report": f"Skill '{skill_name}' not found in your library."}

        skill_data = doc.to_dict()

        # Publish to community registry
        db.collection("skill_registry").document(skill_name).set({
            "name": skill_data["name"],
            "description": skill_data["description"],
            "category": skill_data.get("category", "general"),
            "code_template": skill_data.get("code_template", ""),
            "parameters": skill_data.get("parameters", {}),
            "author": user_id,
            "published_at": time.time(),
        })

        return {
            "status": "success",
            "report": (
                f"Skill '{skill_name}' published to the community registry! "
                "Other Elora users can now discover and install it."
            ),
        }
    except Exception as e:
        return {"status": "error", "report": f"Failed to publish: {e}"}
