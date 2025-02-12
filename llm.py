from litellm import acompletion

from constant import DEFAULT_MODEL, DEFAULT_TEMPERATURE, MAX_OUTPUT_TOKEN, THINK_MAX_OUTPUT_TOKEN
from decorator import log
from utils import estimate_tokens
from models import SearchContext

async def call_llm(
    messages: list[dict[str, str]],
    context: SearchContext,
    response_schema: dict | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
    model: str = DEFAULT_MODEL,
    max_tokens: int = MAX_OUTPUT_TOKEN,
) -> tuple[str, int]:
    """Helper function to make LLM calls using LiteLLM

    Returns:
        str: LLM response
        int: Number of tokens used
    """
    if "gemini/gemini-2.0-flash-thinking-exp-01-21" in model:
        max_tokens = THINK_MAX_OUTPUT_TOKEN

    received_tokens = 0
    for message in messages:
        received_tokens += estimate_tokens(message["content"])
    log.info(f"[LLM call] recived {received_tokens} tokens.")

    try:
        if response_schema:
            response = await acompletion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object", "response_schema": response_schema},
            )
        else:
            response = await acompletion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        text_response: str = response.choices[0].message.content  # type: ignore
        tokens: int = response.usage.total_tokens if hasattr(response, "usage") else 0  # type: ignore
        context.token_usage += tokens
        log.info(f"[LLM call] used {tokens} tokens.")
        return text_response, tokens

    except Exception as e:
        log.error(f"[LLM call] failed: {str(e)}")
        raise
