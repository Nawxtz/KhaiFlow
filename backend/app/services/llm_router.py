import json
import logging
from typing import Any

import httpx

from app.core.config import settings
from app.models.inventory import Inventory
from app.schemas.order import LLMExtractedIntent
from app.services.order_service import product_has_sizes

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def build_catalog_context(products: list[Inventory]) -> str:
    """
    Format catalog metadata for LLM prompt.
    Contains ONLY product metadata (sku, name, category, sizes) - NEVER personal data.
    """
    lines: list[str] = []
    for p in products:
        if not p.active:
            continue
        sizes = product_has_sizes(p)
        size_info = f" (Sizes: {', '.join(sizes)})" if sizes else ""
        cat_info = f" [{p.category}]" if p.category else ""
        lines.append(f"- SKU: {p.sku} | Name: {p.name}{cat_info}{size_info}")
    return "\n".join(lines)


def build_system_prompt(products: list[Inventory]) -> str:
    """Build structured LLM system prompt requesting strict JSON schema output."""
    catalog_str = build_catalog_context(products)
    return (
        "You are an order extraction engine for an e-commerce store. "
        "Your task is to identify which product and quantity the buyer wants to order from the catalog.\n\n"
        "Active Catalog:\n"
        f"{catalog_str}\n\n"
        "Rules:\n"
        "1. Extract the product SKU, name, quantity, and size if requested.\n"
        "2. If the user message is unclear or unrelated to the catalog, set confidence to 0.0.\n"
        "3. You MUST respond with ONLY a valid JSON object matching this exact schema:\n"
        '{\n  "sku": "string or null",\n  "name": "string or null",\n  "qty": 1,\n  "size": "string or null",\n  "confidence": 1.0\n}\n'
        "4. Do NOT include any additional fields like price, status, or notes. Extra fields are strictly forbidden."
    )


def call_openrouter(
    model: str,
    system_prompt: str,
    user_text: str,
    api_key: str | None = None,
    timeout: float = 10.0,
) -> str | None:
    """
    Execute call to OpenRouter API (or compatible OpenAI endpoint).
    Returns raw JSON response text or None on any network/HTTP failure.
    """
    key = api_key or settings.OPENROUTER_API_KEY
    if not key:
        logger.debug("No OpenRouter API key configured; skipping live call.")
        return None

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/nawxtz/Thai-smart-address",
        "X-Title": "Thai Smart Address",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.0,
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(OPENROUTER_URL, headers=headers, json=payload)
            if resp.status_code != 200:
                logger.warning("OpenRouter API returned HTTP %s: %s", resp.status_code, resp.text)
                return None
            data = resp.json()
            choices = data.get("choices")
            if choices and len(choices) > 0:
                content: Any = choices[0].get("message", {}).get("content")
                if isinstance(content, str):
                    return content
            return None
    except Exception as exc:
        logger.warning("Error calling OpenRouter (%s): %s", model, exc)
        return None


def extract_intent_llm(
    text: str,
    products: list[Inventory],
    threshold: float = 0.8,
    api_key: str | None = None,
) -> LLMExtractedIntent | None:
    """
    Extract order intent via LLM router with primary/backup model fallback and strict Pydantic validation.
    On any failure (network, non-JSON, schema violation, low confidence, forbidden fields):
    returns None - NEVER raises to caller.
    """
    try:
        if not text or not text.strip() or not products:
            return None

        system_prompt = build_system_prompt(products)
        models_to_try = [
            settings.LLM_MODEL_MAIN or "gemini/gemini-flash",
            settings.LLM_MODEL_BACKUP or "openai/gpt-4o-mini",
        ]

        raw_response: str | None = None
        for model in models_to_try:
            if not model:
                continue
            raw_response = call_openrouter(
                model=model,
                system_prompt=system_prompt,
                user_text=text.strip(),
                api_key=api_key,
            )
            if raw_response:
                break

        if not raw_response:
            return None

        # Parse JSON
        try:
            parsed_json = json.loads(raw_response)
        except Exception:
            logger.warning("LLM returned non-JSON response: %s", raw_response)
            return None

        if not isinstance(parsed_json, dict):
            return None

        # Validate through strict Pydantic schema (extra="forbid" rejects injected fields)
        try:
            intent = LLMExtractedIntent.model_validate(parsed_json)
        except Exception as exc:
            logger.warning("LLM output schema validation failed: %s", exc)
            return None

        # Check confidence threshold
        if intent.confidence < threshold:
            logger.info("LLM confidence %.2f below threshold %.2f", intent.confidence, threshold)
            return None

        # Check required fields
        if not intent.sku and not intent.name:
            return None

        if intent.qty <= 0:
            return None

        # Validate against live catalog: ensure matched SKU or name belongs to an active product
        matched_product: Inventory | None = None
        for p in products:
            if not p.active:
                continue
            if intent.sku and p.sku.lower() == intent.sku.lower():
                matched_product = p
                break
            if intent.name and p.name.lower() == intent.name.lower():
                matched_product = p
                break

        if not matched_product:
            logger.info(
                "LLM extracted product not found in active catalog: %s / %s",
                intent.sku,
                intent.name,
            )
            return None

        # Overwrite with verified catalog SKU and Name
        intent.sku = matched_product.sku
        intent.name = matched_product.name

        return intent

    except Exception as exc:
        logger.error("Unexpected error in extract_intent_llm: %s", exc)
        return None
