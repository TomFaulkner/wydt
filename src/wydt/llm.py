import os
import logging

logging.basicConfig(level=logging.DEBUG)
httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.DEBUG)

logger = logging.getLogger(__name__)

_client = None
_cheapest_model = None


def _discover_lowest_cost_model() -> str | None:
    """Query the /v1/models endpoint (OpenAI-compatible) and pick a low-cost / lowest-end model.

    Prefers grok-build (cheapest) then current flagships.
    This helps always use the cheapest suitable model available to your account
    instead of relying on a potentially outdated or expensive LLM_MODEL name.
    """
    try:
        from openai import OpenAI

        api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None

        base_url = os.getenv("LLM_BASE_URL", "https://api.x.ai/v1").rstrip("/")
        # Ensure proper /v1 suffix for x.ai
        if "api.x.ai" in base_url and not base_url.rstrip("/").endswith("/v1"):
            base_url = base_url.rstrip("/") + "/v1"

        temp_client = OpenAI(api_key=api_key, base_url=base_url)
        resp = temp_client.models.list()
        ids = [m.id for m in getattr(resp, "data", [])]
        if not ids:
            return None

        logger.info(f"Discovered {len(ids)} models via API")

        # Preference for lowest-cost models based on current xAI pricing.
        # grok-build-0.1 is the cheapest ($1/$2). Then grok-4.3 and 4.20 variants
        # (all ~$1.25/$2.50). Prioritize build first per request.
        priority_checks = [
            lambda i: "build" in i.lower() or "code-fast" in i.lower(),
            lambda i: "grok-4.3" in i.lower(),
            lambda i: "4.20" in i and "reasoning" in i.lower(),
            lambda i: "grok-4.20-reasoning" in i.lower(),
            lambda i: "4.20" in i and "non-reasoning" in i.lower(),
            lambda i: "grok-4.20-non-reasoning" in i.lower(),
            lambda i: "fast-non-reasoning" in i.lower(),
            lambda i: "fast" in i.lower(),
            lambda i: "non-reasoning" in i.lower(),
            lambda i: "mini" in i.lower(),
            lambda i: "grok-3" in i.lower(),
        ]

        for check in priority_checks:
            for model_id in ids:
                if check(model_id):
                    logger.info(f"Auto-selected lowest-cost model: {model_id}")
                    return model_id

        # Fallback: prefer grok-4.3 or any recent grok-4.x if present, else first
        for preferred in ("grok-4.3", "grok-4.20", "grok-4"):
            for model_id in ids:
                if preferred in model_id.lower():
                    return model_id
        return ids[0] if ids else None
    except Exception as e:
        logger.warning(f"Could not discover models list for lowest-cost selection: {e}")
        return None


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI

        api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("LLM_BASE_URL", "").rstrip("/")

        if base_url.startswith("http://"):
            base_url = base_url.replace("http://", "https://", 1)
            logger.warning(f"Changed HTTP to HTTPS for LLM_BASE_URL: {base_url}")

        logger.info("Initializing OpenAI client:")
        logger.info(f"  base_url: {base_url}")
        logger.info(f"  model: {_get_model()}")
        logger.info(f"  api_key: {api_key[:10] if api_key else 'None'}...")

        _client = OpenAI(api_key=api_key, base_url=base_url)
    return _client


def _get_model():
    explicit = os.getenv("LLM_MODEL", "").strip()
    if explicit:
        return explicit

    # No explicit LLM_MODEL set -> dynamically pick the lowest-cost model
    # available to this account via the models API. This is the recommended
    # way to "always use the lowest end model".
    global _cheapest_model
    if _cheapest_model is None:
        discovered = _discover_lowest_cost_model()
        if discovered:
            _cheapest_model = discovered
        else:
            # Sensible fallback based on base URL
            base_url = os.getenv("LLM_BASE_URL", "")
            if "x.ai" in base_url:
                _cheapest_model = "grok-build-0.1"
            else:
                _cheapest_model = "gpt-4o-mini"
    return _cheapest_model


def _get_reasoning_effort(model: str) -> str | None:
    """For basic summaries, use 'low' reasoning effort on models that support it.
    This reduces cost and latency for simple tasks like journal summaries.
    Returns None for models that don't use/support it (e.g. build variants).
    """
    m = model.lower()
    if "build" in m or "code-fast" in m:
        return None
    # grok-4.3, grok-4.20 etc. support reasoning_effort
    if any(k in m for k in ["4.3", "4.20", "grok-4"]):
        return "low"
    return None


def generate_summary_and_keywords(content: str) -> tuple[str, str, str | None]:
    if not content or not content.strip():
        return ("", "", None)
    try:
        client = _get_client()
        model = _get_model()
        logger.info(f"Generating summary and keywords with model: {model}")

        kwargs = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": """You are a helpful assistant that processes daily journal entries.
Analyze the entry and provide:
1. A brief 1-2 sentence summary of what the person did that day
2. A comma-separated list of 3-8 relevant keywords/tags for searching

Format your response as:
SUMMARY: <summary text>
KEYWORDS: <keyword1>, <keyword2>, <keyword3>, ...""",
                },
                {
                    "role": "user",
                    "content": f"Process this daily log:\n\n{content}",
                },
            ],
            "max_tokens": 150,
        }
        if effort := _get_reasoning_effort(model):
            kwargs["extra_body"] = {"reasoning_effort": effort}
        response = client.chat.completions.create(**kwargs)
        result = response.choices[0].message.content.strip()

        summary = ""
        keywords = ""

        for line in result.split("\n"):
            if line.startswith("SUMMARY:"):
                summary = line[8:].strip()
            elif line.startswith("KEYWORDS:"):
                keywords = line[9:].strip()

        if not summary and not keywords:
            summary = result

        logger.info(f"Generated summary: {summary[:50]}..., keywords: {keywords}")
        return (summary, keywords, None)
    except Exception as e:
        logger.exception(f"Error generating summary: {e}")
        return ("", "", str(e))


def generate_summary(content: str) -> str:
    summary, _, _ = generate_summary_and_keywords(content)
    return summary


def generate_weekly_summary(logs_data: list[dict]) -> dict:
    """
    Generate a weekly summary from daily logs.

    Args:
        logs_data: List of dicts with 'date', 'content', 'summary', 'keywords' keys

    Returns:
        Dict with 'summary', 'themes', 'accomplishments', 'highlights', 'references' keys
    """
    if not logs_data:
        return {
            "summary": "",
            "themes": "",
            "accomplishments": "",
            "highlights": "",
            "references": "",
            "error": None,
        }

    try:
        client = _get_client()
        model = _get_model()
        logger.info(f"Generating weekly summary with model: {model}")

        # Format logs for the prompt
        logs_text = "\n\n".join(
            [
                f"Date: {log['date']}\nSummary: {log['summary']}\nContent: {log['content'][:500]}"
                for log in logs_data
            ]
        )

        kwargs = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": """You are a helpful assistant that creates weekly summaries from daily journal entries.
Analyze the week's entries and provide:

1. A brief 2-3 sentence overall summary of the week
2. Key themes or focus areas for the week (comma-separated list)
3. Major accomplishments or completed tasks (bullet points, one per line)
4. Notable highlights or interesting moments (bullet points, one per line)
5. Any ticket numbers, IDs, references, or identifiers mentioned (e.g., #123, ABC-456, PR-789, etc.) - comma-separated list

Be concise but informative. Look for patterns across the week.

Format your response exactly as:
SUMMARY: <overall summary text>
THEMES: <theme1>, <theme2>, ...
ACCOMPLISHMENTS:
- <accomplishment 1>
- <accomplishment 2>
HIGHLIGHTS:
- <highlight 1>
- <highlight 2>
REFERENCES: <reference1>, <reference2>, ... (or "None" if no identifiers found)""",
                },
                {
                    "role": "user",
                    "content": f"Create a weekly summary from these daily entries:\n\n{logs_text}",
                },
            ],
            "max_tokens": 500,
        }
        if effort := _get_reasoning_effort(model):
            kwargs["extra_body"] = {"reasoning_effort": effort}
        response = client.chat.completions.create(**kwargs)
        result = response.choices[0].message.content.strip()

        # Parse the response
        output = {
            "summary": "",
            "themes": "",
            "accomplishments": "",
            "highlights": "",
            "references": "",
        }

        current_section = None
        current_value = []

        for line in result.split("\n"):
            line = line.strip()
            if not line:
                continue

            if line.startswith("SUMMARY:"):
                if current_section:
                    output[current_section] = "\n".join(current_value).strip()
                current_section = "summary"
                current_value = [line[8:].strip()]
            elif line.startswith("THEMES:"):
                if current_section:
                    output[current_section] = "\n".join(current_value).strip()
                current_section = "themes"
                current_value = [line[7:].strip()]
            elif line.startswith("ACCOMPLISHMENTS:"):
                if current_section:
                    output[current_section] = "\n".join(current_value).strip()
                current_section = "accomplishments"
                current_value = []
            elif line.startswith("HIGHLIGHTS:"):
                if current_section:
                    output[current_section] = "\n".join(current_value).strip()
                current_section = "highlights"
                current_value = []
            elif line.startswith("REFERENCES:"):
                if current_section:
                    output[current_section] = "\n".join(current_value).strip()
                current_section = "references"
                current_value = [line[11:].strip()]
            elif line.startswith("-") and current_section in [
                "accomplishments",
                "highlights",
            ]:
                current_value.append(line[1:].strip())
            elif current_section:
                current_value.append(line)

        if current_section:
            output[current_section] = "\n".join(current_value).strip()

        # Clean up references - remove "None" text
        if output["references"].lower() == "none":
            output["references"] = ""

        logger.info(f"Generated weekly summary: {output['summary'][:50]}...")
        output["error"] = None
        return output

    except Exception as e:
        logger.exception(f"Error generating weekly summary: {e}")
        return {
            "summary": "",
            "themes": "",
            "accomplishments": "",
            "highlights": "",
            "references": "",
            "error": str(e),
        }
