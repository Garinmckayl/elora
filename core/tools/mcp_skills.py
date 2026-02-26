"""
MCP + skills.md dynamic API connection system.
Allows Elora to connect to any external API by reading skill definitions
and executing commands in an E2B sandbox.
"""

import os
import logging
import json

logger = logging.getLogger("elora-tools.mcp_skills")

E2B_API_KEY = os.getenv("E2B_API_KEY", "")


# Default skills that Elora knows about
DEFAULT_SKILLS = """
# Elora Skills

## Weather API
- endpoint: https://api.open-meteo.com/v1/forecast
- method: GET
- params: latitude, longitude, current_weather=true
- example: curl "https://api.open-meteo.com/v1/forecast?latitude=40.71&longitude=-74.01&current_weather=true"
- no auth required

## GitHub API
- endpoint: https://api.github.com
- method: GET/POST
- auth: Bearer token via GITHUB_TOKEN env var
- example: curl -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/user

## News API
- endpoint: https://newsapi.org/v2/top-headlines
- method: GET
- params: country, category, q (query)
- auth: apiKey query parameter
- example: curl "https://newsapi.org/v2/top-headlines?country=us&apiKey=$NEWS_API_KEY"

## Exchange Rates
- endpoint: https://api.exchangerate-api.com/v4/latest/USD
- method: GET
- no auth required
- example: curl https://api.exchangerate-api.com/v4/latest/USD

## Joke API
- endpoint: https://official-joke-api.appspot.com/random_joke
- method: GET  
- no auth required

## REST Countries
- endpoint: https://restcountries.com/v3.1
- paths: /name/{name}, /alpha/{code}, /all
- method: GET
- no auth required
"""


def execute_skill(
    skill_description: str,
    code: str,
    language: str = "python",
    timeout: int = 30,
) -> dict:
    """Execute a skill/API call in a sandboxed environment.

    This allows Elora to connect to ANY external API by running code
    in an isolated sandbox. The code can make HTTP requests, parse responses,
    and return structured results.

    Args:
        skill_description: Brief description of what this skill does.
        code: Python or JavaScript code to execute. Should print the result as JSON.
        language: 'python' or 'javascript'.
        timeout: Max execution time in seconds (5-120).

    Returns:
        dict with execution results.
    """
    try:
        from tools.e2b_sandbox import run_code
        result = run_code(code, language, min(max(timeout, 5), 120))

        if result.get("status") == "success":
            return {
                "status": "success",
                "skill": skill_description,
                "output": result.get("stdout", ""),
                "report": f"Skill '{skill_description}' executed successfully.",
            }
        else:
            return {
                "status": "error",
                "skill": skill_description,
                "error": result.get("stderr", result.get("report", "Unknown error")),
                "report": f"Skill '{skill_description}' failed: {result.get('stderr', '')[:200]}",
            }

    except Exception as e:
        logger.error(f"Skill execution failed: {e}")
        return {
            "status": "error",
            "report": f"Skill execution failed: {str(e)[:200]}",
        }


def list_available_skills() -> dict:
    """List all available skills/API connections that Elora can use.

    Returns:
        dict with available skills and their descriptions.
    """
    return {
        "status": "success",
        "skills": DEFAULT_SKILLS,
        "report": (
            "Available skills: Weather API, GitHub API, News API, "
            "Exchange Rates, Joke API, REST Countries. "
            "I can also connect to any API by writing code to call it in my sandbox."
        ),
    }


def install_skill(
    name: str,
    description: str,
    endpoint: str,
    method: str = "GET",
    auth_type: str = "none",
    example: str = "",
) -> dict:
    """Register a new API skill that Elora can use.

    Args:
        name: Name of the skill/API.
        description: What this API does.
        endpoint: Base URL of the API.
        method: HTTP method (GET, POST, etc.).
        auth_type: Authentication type (none, bearer, api_key, basic).
        example: Example usage.

    Returns:
        dict with registration status.
    """
    # In a full implementation, this would persist to Firestore
    # For now, acknowledge the registration
    return {
        "status": "success",
        "report": (
            f"Skill '{name}' registered. I can now use {endpoint} "
            f"via {method}. I'll execute calls in my sandbox environment."
        ),
    }
