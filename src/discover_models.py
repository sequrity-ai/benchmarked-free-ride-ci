#!/usr/bin/env python3
"""
Discover free models from OpenRouter API.
Similar to FreeRide's model discovery, but focuses on benchmark-ready models.
"""

import os
import json
import requests
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path


OPENROUTER_API_URL = "https://openrouter.ai/api/v1/models"


def fetch_all_models(api_key: str) -> List[Dict[str, Any]]:
    """Fetch all models from OpenRouter API."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(OPENROUTER_API_URL, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json().get("data", [])
    except Exception as e:
        print(f"Error fetching models: {e}")
        return []


def is_free_model(model: Dict[str, Any]) -> bool:
    """Check if a model is free."""
    pricing = model.get("pricing", {})
    prompt_price = float(pricing.get("prompt", 1))
    completion_price = float(pricing.get("completion", 1))

    # Model is free if both prompt and completion are $0
    # OR if it has :free suffix
    model_id = model.get("id", "")
    return (prompt_price == 0 and completion_price == 0) or ":free" in model_id


def score_model(model: Dict[str, Any]) -> float:
    """
    Score a model based on context length, capabilities, recency, and provider trust.
    Uses the same weighted scoring as FreeRide.
    """
    # Context length score (40% weight)
    context_length = model.get("context_length", 4096)
    context_score = min(context_length / 1_000_000, 1.0) * 0.4

    # Capabilities score (30% weight)
    # Count supported parameters as proxy for capabilities
    architecture = model.get("architecture", {})
    capabilities = len([v for v in architecture.values() if v]) if architecture else 0
    capabilities_score = min(capabilities / 10, 1.0) * 0.3

    # Recency score (20% weight)
    # Newer models get higher scores (decay over 365 days)
    created_str = model.get("created", 0)
    if isinstance(created_str, (int, float)):
        created = created_str
    else:
        created = 0

    now = datetime.now().timestamp()
    days_old = (now - created) / 86400 if created > 0 else 365
    recency_score = max(1.0 - (days_old / 365), 0) * 0.2

    # Provider trust score (10% weight)
    model_id = model.get("id", "")
    trusted_providers = [
        "google", "meta-llama", "mistralai", "anthropic",
        "openai", "cohere", "01-ai", "microsoft"
    ]
    provider_score = 0.1 if any(p in model_id.lower() for p in trusted_providers) else 0.05

    total_score = context_score + capabilities_score + recency_score + provider_score
    return round(total_score, 4)


def filter_benchmark_compatible(models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filter models that are suitable for benchmarking.
    Exclude models that are:
    - Image/vision only models
    - Audio/speech models
    - Embedding models
    - Models with very small context (<4k tokens)
    """
    compatible = []

    for model in models:
        model_id = model.get("id", "")
        context_length = model.get("context_length", 0)

        # Skip non-text models
        skip_keywords = ["vision", "image", "audio", "speech", "whisper", "embedding", "clip"]
        if any(keyword in model_id.lower() for keyword in skip_keywords):
            continue

        # Require minimum 4k context
        if context_length < 4096:
            continue

        compatible.append(model)

    return compatible


def select_top_models(models: List[Dict[str, Any]], limit: int = 10) -> List[Dict[str, Any]]:
    """Select top N models by score."""
    # Score all models
    scored_models = [
        {**model, "quality_score": score_model(model)}
        for model in models
    ]

    # Sort by score descending
    scored_models.sort(key=lambda m: m["quality_score"], reverse=True)

    return scored_models[:limit]


def save_discovered_models(models: List[Dict[str, Any]], output_dir: Path):
    """Save discovered models to JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save full model data
    output_file = output_dir / "discovered_models.json"
    with open(output_file, "w") as f:
        json.dump({
            "discovered_at": datetime.now().isoformat(),
            "total_models": len(models),
            "models": models
        }, f, indent=2)

    print(f"Saved {len(models)} models to {output_file}")

    # Also save just model IDs for easy iteration
    model_ids_file = output_dir / "discovered_models.txt"
    with open(model_ids_file, "w") as f:
        for model in models:
            f.write(f"{model['id']}\n")

    print(f"Saved model IDs to {model_ids_file}")


def main():
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("Error: OPENROUTER_API_KEY environment variable not set")
        exit(1)

    print("Fetching models from OpenRouter...")
    all_models = fetch_all_models(api_key)
    print(f"Found {len(all_models)} total models")

    print("\nFiltering for free models...")
    free_models = [m for m in all_models if is_free_model(m)]
    print(f"Found {len(free_models)} free models")

    print("\nFiltering for benchmark-compatible models...")
    compatible_models = filter_benchmark_compatible(free_models)
    print(f"Found {len(compatible_models)} benchmark-compatible models")

    print("\nSelecting top 20 models by quality score...")
    top_models = select_top_models(compatible_models, limit=20)

    print("\nTop 20 models:")
    for i, model in enumerate(top_models, 1):
        print(f"{i}. {model['id']} (score: {model['quality_score']}, context: {model.get('context_length', 0)})")

    print("\nSaving results...")
    output_dir = Path("output")
    save_discovered_models(top_models, output_dir)

    print("\nDone!")


if __name__ == "__main__":
    main()
