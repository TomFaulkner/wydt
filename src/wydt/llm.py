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
