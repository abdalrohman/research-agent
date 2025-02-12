import re

import cachetools  # type: ignore
import tiktoken

encoding = tiktoken.get_encoding("cl100k_base")


@cachetools.cached(cache=cachetools.TTLCache(maxsize=1000, ttl=3600))
def estimate_tokens(text: str) -> int:
    return len(encoding.encode(text))


def remove_extra_line_breaks(text: str) -> str:
    """The function ensures consistent spacing by preventing excessive empty lines."""
    return re.sub(r"\n{2,}", "\n\n", text)
