import os
import logging

logging.basicConfig(level=logging.DEBUG)
httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.DEBUG)

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI

        api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("LLM_BASE_URL", "").rstrip("/")

        if base_url.startswith("http://"):
            base_url = base_url.replace("http://", "https://", 1)
            logger.warning(f"Changed HTTP to HTTPS for LLM_BASE_URL: {base_url}")

        logger.info(f"Initializing OpenAI client:")
        logger.info(f"  base_url: {base_url}")
        logger.info(f"  model: {_get_model()}")
        logger.info(f"  api_key: {api_key[:10] if api_key else 'None'}...")

        _client = OpenAI(api_key=api_key, base_url=base_url)
    return _client


def _get_model():
    model = os.getenv("LLM_MODEL")
    if model:
        return model
    base_url = os.getenv("LLM_BASE_URL", "")
    if "x.ai" in base_url:
        return "grok-beta"
    return "gpt-4o-mini"


def generate_summary_and_keywords(content: str) -> tuple[str, str]:
    if not content or not content.strip():
        return ("", "")
    try:
        client = _get_client()
        model = _get_model()
        logger.info(f"Generating summary and keywords with model: {model}")

        response = client.chat.completions.create(
            model=model,
            messages=[
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
            max_tokens=150,
        )
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
        return (summary, keywords)
    except Exception as e:
        logger.exception(f"Error generating summary: {e}")
        return ("", "")


def generate_summary(content: str) -> str:
    summary, _ = generate_summary_and_keywords(content)
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

        response = client.chat.completions.create(
            model=model,
            messages=[
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
            max_tokens=500,
        )
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
        return output

    except Exception as e:
        logger.exception(f"Error generating weekly summary: {e}")
        return {
            "summary": "",
            "themes": "",
            "accomplishments": "",
            "highlights": "",
            "references": "",
        }
