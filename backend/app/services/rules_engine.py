import logging
import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from app.models.inventory import Inventory
from app.services.order_service import product_has_sizes

logger = logging.getLogger(__name__)

# Common size tokens (case-insensitive)
SIZE_TOKENS = ["XS", "S", "M", "L", "XL", "2XL", "XXL", "3XL"]


@dataclass
class RuleMatchResult:
    product: Inventory
    sku: str
    name: str
    qty: int
    size: str | None
    confidence: float


def extract_quantity(text: str) -> tuple[int, str]:
    """
    Extract integer quantity from text (e.g. '2 pcs', 'x2', or trailing number).
    Returns (quantity, remaining_cleaned_text). Defaults to qty=1.
    """
    cleaned = text.strip()

    # Pattern 1: Explicit multiplier like x2, x 2, *2
    match = re.search(r"(?:^|\s)[xX*]\s*(\d+)(?:\s|$)", cleaned)
    if match:
        qty = int(match.group(1))
        remaining = cleaned[: match.start()] + " " + cleaned[match.end() :]
        return (max(1, qty), remaining.strip())

    # Pattern 2: Number followed by unit or Thai classifier (\u0e0a\u0e34\u0e49\u0e19, \u0e15\u0e31\u0e27, etc.)
    unit_pattern = r"(?:^|\s)(\d+)\s*(?:pcs?|items?|packs?|qty|ea|[\u0e0a\u0e34\u0e49\u0e19\u0e15\u0e31\u0e27\u0e1c\u0e37\u0e48\u0e19\u0e2d\u0e31\u0e19\u0e0a\u0e38\u0e14\u0e43\u0e1a\u0e01\u0e25\u0e48\u0e2d\u0e07\u0e41\u0e1e\u0e47\u0e04])(?:\s|$)"
    match = re.search(unit_pattern, cleaned, re.IGNORECASE)
    if match:
        qty = int(match.group(1))
        remaining = cleaned[: match.start()] + " " + cleaned[match.end() :]
        return (max(1, qty), remaining.strip())

    # Pattern 3: Standalone number at the end of text (e.g., 'Silk Scarf 2')
    match = re.search(r"(?:^|\s)(\d+)$", cleaned)
    if match:
        qty = int(match.group(1))
        remaining = cleaned[: match.start()]
        return (max(1, qty), remaining.strip())

    return (1, cleaned)


def extract_size(text: str, allowed_sizes: list[str] | None = None) -> tuple[str | None, str]:
    """
    Extract size variant from text (e.g. 'size M', 'Size: L', or standalone size token).
    Returns (size, remaining_cleaned_text).
    """
    cleaned = text.strip()
    valid_sizes = allowed_sizes if allowed_sizes else SIZE_TOKENS

    # Check for 'size <token>' or 'size: <token>'
    match = re.search(r"(?:size|sz)[\s:]*([a-zA-Z0-9]+)", cleaned, re.IGNORECASE)
    if match:
        candidate = match.group(1).upper()
        if candidate in valid_sizes:
            remaining = cleaned[: match.start()] + " " + cleaned[match.end() :]
            return (candidate, remaining.strip())

    # Check for standalone size token surrounded by word boundaries
    for sz in sorted(valid_sizes, key=len, reverse=True):
        pattern = rf"(?:^|\s)({re.escape(sz)})(?:\s|$)"
        match = re.search(pattern, cleaned, re.IGNORECASE)
        if match:
            remaining = cleaned[: match.start()] + " " + cleaned[match.end() :]
            return (sz, remaining.strip())

    return (None, cleaned)


def match_product_rules(
    text: str,
    products: list[Inventory],
    threshold: float = 0.8,
) -> RuleMatchResult | None:
    """
    RapidFuzz token-sort-ratio matching against product name and category from inventory.
    Returns RuleMatchResult if top match confidence >= threshold, else None.
    """
    if not text or not products:
        return None

    qty, query_without_qty = extract_quantity(text)
    size, query_cleaned = extract_size(query_without_qty)

    best_product: Inventory | None = None
    best_score: float = 0.0

    for product in products:
        if not product.active:
            continue

        # Match against product name
        name_score = fuzz.token_sort_ratio(query_cleaned, product.name)

        # Match against name + category
        cat_score = 0.0
        if product.category:
            full_target = f"{product.name} {product.category}"
            cat_score = fuzz.token_sort_ratio(query_cleaned, full_target)

        # Also check with raw text
        raw_name_score = fuzz.token_sort_ratio(text, product.name)

        score = max(name_score, cat_score, raw_name_score)
        if score > best_score:
            best_score = score
            best_product = product

    confidence = best_score / 100.0

    if best_product and confidence >= threshold:
        has_sizes = product_has_sizes(best_product)
        final_size = (
            size
            if (size and (not has_sizes or size in has_sizes))
            else (has_sizes[0] if has_sizes and not size else size)
        )

        return RuleMatchResult(
            product=best_product,
            sku=best_product.sku,
            name=best_product.name,
            qty=qty,
            size=final_size,
            confidence=confidence,
        )

    return None
