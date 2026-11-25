import logging
import os
import uuid

logging.basicConfig(level=logging.DEBUG)
httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.DEBUG)

logger = logging.getLogger(__name__)

_client = None
_cheapest_model = None
_reasoning_effort_supported = False
_session_id = None

# OpenCode Console inference API - OpenAI-compatible (chat/completions, /models).
# Model catalog: https://opencode.ai/docs/console/models
DEFAULT_BASE_URL = "https://opencode.ai/inference/v1"

# Each daily log is truncated to this many characters before it goes into the
# weekly summary request.
_WEEKLY_LOG_CHARS = 500


def _get_api_key() -> str | None:
    """Console key first, then the generic OpenAI-compatible vars."""
    return (
        os.getenv("OPENCODE_API_KEY")
        or os.getenv("LLM_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )


def _get_base_url() -> str:
    base_url = os.getenv("LLM_BASE_URL", "").strip().rstrip("/")

    if base_url.startswith("http://"):
        base_url = base_url.replace("http://", "https://", 1)
        logger.warning(f"Changed HTTP to HTTPS for LLM_BASE_URL: {base_url}")

    return base_url or DEFAULT_BASE_URL


def _allow_training_models() -> bool:
    return os.getenv("LLM_ALLOW_TRAINING_MODELS", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _allow_free_models() -> bool:
    return os.getenv("LLM_ALLOW_FREE_MODELS", "").strip().lower() in ("1", "true", "yes")


def _rank_candidates(models: list) -> list[tuple[str, float, bool]]:
    """Turn /v1/models entries into (id, input+output price per 1M tokens, supports reasoning effort).

    The OpenCode inference list carries models.dev pricing, so the cheapest model
    is picked by real cost instead of guessing from the model name. Only chat
    models are considered, and anything without pricing can't be ranked.
    """
    candidates: list[tuple[str, float, bool]] = []

    for m in models:
        extra = getattr(m, "model_extra", None) or {}
        if extra.get("type", "chat") != "chat":
            continue

        text = (extra.get("cost") or {}).get("text") or {}
        input_price = (text.get("input") or {}).get("price")
        output_price = (text.get("output") or {}).get("price")
        if input_price is None or output_price is None:
            continue

        # Contributor/free tiers can train on requests; journal entries
        # shouldn't go to them unless explicitly allowed.
        go = extra.get("go") or {}
        if go.get("training") and not _allow_training_models():
            continue

        reasoning = (extra.get("capabilities") or {}).get("reasoning") or {}
        candidates.append(
            (m.id, float(input_price) + float(output_price), bool(reasoning.get("effort")))
        )

    return candidates


def _extra_headers(base_url: str) -> dict:
    """Headers OpenCode expects from clients that aren't OpenCode itself.

    The OpenCode Go provider rejects requests without a stable session ID, and
    asks clients to identify themselves instead of using a generic SDK UA.
    See https://opencode.ai/docs/console/go#where-can-i-use-it
    """
    if "opencode.ai" not in base_url:
        return {}

    global _session_id
    if _session_id is None:
        # One stable ID per process: every summary shares the same system
        # prompt, so keeping it stable lets OpenCode cache the prefix.
        _session_id = os.getenv("LLM_SESSION_ID", "").strip() or f"ses_{uuid.uuid4()}"

    return {
        "User-Agent": os.getenv("LLM_USER_AGENT", "").strip() or "wydt/0.1.0",
        "x-opencode-session": _session_id,
    }


def _discover_lowest_cost_model() -> tuple[str | None, bool]:
    """Query the /v1/models endpoint and pick the cheapest available chat model.

    Returns (model_id, supports_reasoning_effort).
    """
    try:
        api_key = _get_api_key()
        if not api_key:
            logger.warning(
                "No API key set (OPENCODE_API_KEY / LLM_API_KEY); skipping model discovery"
            )
            return (None, False)

        from openai import OpenAI

        temp_client = OpenAI(
            api_key=api_key,
            base_url=_get_base_url(),
            default_headers=_extra_headers(_get_base_url()),
        )
        resp = temp_client.models.list()
        models = list(getattr(resp, "data", []))
        if not models:
            return (None, False)

        logger.info(f"Discovered {len(models)} models via API")

        candidates = _rank_candidates(models)
        if not candidates:
            logger.warning(
                "No models with pricing info returned; falling back to the first listed model"
            )
            return (models[0].id, False)

        # Free-tier chat models only serve OpenCode itself, so skip them unless
        # explicitly allowed.
        paid = [c for c in candidates if c[1] > 0]
        if paid:
            pool = paid
        else:
            logger.warning(
                "Only free-tier models are available to this key; set "
                "LLM_ALLOW_FREE_MODELS=1 to try them anyway (they may be rejected)"
            )
            if not _allow_free_models():
                return (None, False)
            pool = candidates

        cheapest = min(pool, key=lambda c: c[1])
        logger.info(
            f"Auto-selected lowest-cost model: {cheapest[0]} "
            f"(${cheapest[1]:g}/1M in+out tokens)"
        )
        return (cheapest[0], cheapest[2])
    except Exception as e:
        logger.warning(f"Could not discover models list for lowest-cost selection: {e}")
        return (None, False)


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI

        api_key = _get_api_key()
        base_url = _get_base_url()

        logger.info("Initializing OpenAI client:")
        logger.info(f"  base_url: {base_url}")
        logger.info(f"  model: {_get_model()}")
        logger.info(f"  api_key: {api_key[:10] if api_key else 'None'}...")

        _client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers=_extra_headers(base_url),
        )
    return _client


def _get_model():
    explicit = os.getenv("LLM_MODEL", "").strip()
    if explicit:
        return explicit

    # No explicit LLM_MODEL set -> dynamically pick the lowest-cost model
    # available to this account via the models API. This is the recommended
    # way to "always use the lowest end model".
    global _cheapest_model
    global _reasoning_effort_supported
    if _cheapest_model is None:
        discovered, supports_reasoning_effort = _discover_lowest_cost_model()
        if discovered:
            _cheapest_model = discovered
            _reasoning_effort_supported = supports_reasoning_effort
        else:
            # Sensible fallback if discovery is unavailable
            _cheapest_model = (
                "gpt-5-nano" if "opencode.ai" in _get_base_url() else "gpt-4o-mini"
            )
            _reasoning_effort_supported = False
    return _cheapest_model


def _system_prompt(key: str) -> str:
    """Load a prompt from the database, falling back to the built-in default."""
    return _prompt(key)


def _user_prompt(key: str, **values: str) -> str:
    """Load a user-message template and fill its placeholders."""
    template = _prompt(key)
    try:
        from .models import render_prompt

        return render_prompt(template, **values)
    except Exception as e:
        logger.warning(f"Could not render prompt '{key}': {e}")
        return template


def _prompt(key: str) -> str:
    """Load a prompt from the database, falling back to the built-in default."""
    try:
        from .models import Prompt

        return Prompt.get_text(key)
    except Exception as e:
        logger.warning(f"Could not load prompt '{key}' from DB, using default: {e}")
        from .models import DEFAULT_PROMPTS

        return DEFAULT_PROMPTS.get(key, ("", ""))[1]


def _get_reasoning_effort(model: str) -> str | None:
    """For basic summaries, use 'low' reasoning effort on models that support it.

    This reduces cost and latency for simple tasks like journal summaries.
    Support is only known for auto-discovered models, so an explicit LLM_MODEL
    gets none unless LLM_REASONING_EFFORT says otherwise.
    """
    override = os.getenv("LLM_REASONING_EFFORT", "").strip().lower()
    if override in ("none", "off", "false"):
        return None
    if override:
        return override
    return "low" if _reasoning_effort_supported else None


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
                    "content": _system_prompt("daily_summary"),
                },
                {
                    "role": "user",
                    "content": _user_prompt("daily_summary_user", content=content),
                },
            ],
            # Reasoning models spend part of the budget on thinking tokens, so
            # leave room for the actual answer.
            "max_tokens": 1000,
        }
        if effort := _get_reasoning_effort(model):
            kwargs["reasoning_effort"] = effort
        response = client.chat.completions.create(**kwargs)
        result = (response.choices[0].message.content or "").strip()

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

        # Format logs for the prompt, using the editable per-entry template
        from .models import render_prompt

        log_template = _prompt("weekly_log_entry")
        logs_text = "\n\n".join(
            render_prompt(
                log_template,
                date=log["date"],
                summary=log["summary"],
                content=log["content"][: _WEEKLY_LOG_CHARS],
            )
            for log in logs_data
        )

        kwargs = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": _system_prompt("weekly_summary"),
                },
                {
                    "role": "user",
                    "content": _user_prompt("weekly_summary_user", logs=logs_text),
                },
            ],
            "max_tokens": 2000,
        }
        if effort := _get_reasoning_effort(model):
            kwargs["reasoning_effort"] = effort
        response = client.chat.completions.create(**kwargs)
        result = (response.choices[0].message.content or "").strip()

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
