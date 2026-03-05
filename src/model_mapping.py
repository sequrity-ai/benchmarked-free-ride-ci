"""Map OpenRouter model IDs to AgentDojo-compatible model names.

AgentDojo uses specific model names (e.g., 'gpt-4o-2024-05-13', 'claude-3-opus-20240229').
This module maps OpenRouter free model IDs to their equivalent AgentDojo model names.
"""

from typing import Dict, Optional

# OpenRouter model ID -> AgentDojo model name
OPENROUTER_TO_AGENTDOJO: Dict[str, str] = {
    # OpenAI models
    "openai/gpt-4o": "gpt-4o-2024-05-13",
    "openai/gpt-4o-mini": "gpt-4o-mini-2024-07-18",
    "openai/gpt-3.5-turbo": "gpt-3.5-turbo-0125",

    # Anthropic Claude models
    "anthropic/claude-3-opus": "claude-3-opus-20240229",
    "anthropic/claude-3-sonnet": "claude-3-sonnet-20240229",
    "anthropic/claude-3-haiku": "claude-3-haiku-20240307",
    "anthropic/claude-3.5-sonnet": "claude-3-5-sonnet-20241022",

    # Google Gemini models
    "google/gemini-pro": "gemini-1.5-pro-001",
    "google/gemini-flash": "gemini-1.5-flash-001",
    "google/gemini-2.0-flash-exp:free": "gemini-2.0-flash-exp",

    # Meta Llama models
    "meta-llama/llama-3-70b-instruct": "llama-3-70b-instruct",
    "meta-llama/llama-3.1-70b-instruct": "llama-3.1-70b-instruct",
    "meta-llama/llama-3.1-405b-instruct": "llama-3.1-405b-instruct",

    # Mistral models
    "mistralai/mistral-7b-instruct": "mistral-7b-instruct-v0.3",
    "mistralai/mixtral-8x7b-instruct": "mixtral-8x7b-instruct-v0.1",
    "mistralai/mistral-large": "mistral-large-2407",

    # Cohere models
    "cohere/command-r-plus": "command-r-plus",
    "cohere/command-r": "command-r",
}


def map_openrouter_to_agentdojo(openrouter_id: str) -> Optional[str]:
    """Map an OpenRouter model ID to its AgentDojo equivalent.

    Args:
        openrouter_id: OpenRouter model ID (e.g., 'google/gemini-2.0-flash-exp:free')

    Returns:
        AgentDojo model name if mapping exists, otherwise None
    """
    # Direct match
    if openrouter_id in OPENROUTER_TO_AGENTDOJO:
        return OPENROUTER_TO_AGENTDOJO[openrouter_id]

    # Try without :free suffix
    base_id = openrouter_id.replace(":free", "")
    if base_id in OPENROUTER_TO_AGENTDOJO:
        return OPENROUTER_TO_AGENTDOJO[base_id]

    # Try fuzzy matching for similar models
    for or_id, ad_model in OPENROUTER_TO_AGENTDOJO.items():
        # Match by base model name (e.g., "gpt-4o" in "openai/gpt-4o-2024-08-06")
        or_base = or_id.split("/")[-1].split("-")[0:2]  # ["gpt", "4o"]
        input_base = openrouter_id.split("/")[-1].split("-")[0:2]
        if or_base == input_base:
            return ad_model

    return None


def is_model_supported_for_safety(openrouter_id: str) -> bool:
    """Check if a model can be tested with AgentDojo safety benchmark.

    Args:
        openrouter_id: OpenRouter model ID

    Returns:
        True if model has an AgentDojo mapping, False otherwise
    """
    return map_openrouter_to_agentdojo(openrouter_id) is not None


def get_supported_models() -> Dict[str, str]:
    """Get all supported OpenRouter -> AgentDojo mappings.

    Returns:
        Dictionary of OpenRouter ID -> AgentDojo model name
    """
    return OPENROUTER_TO_AGENTDOJO.copy()
