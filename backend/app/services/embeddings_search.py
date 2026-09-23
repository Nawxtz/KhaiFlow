import logging
import math
import re
from collections import Counter
from dataclasses import dataclass

from app.models.inventory import Inventory
from app.services.order_service import product_has_sizes
from app.services.rules_engine import extract_quantity, extract_size

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingSearchResult:
    product: Inventory
    sku: str
    name: str
    qty: int
    size: str | None
    confidence: float


def _tokenize(text: str) -> list[str]:
    """
    Generate tokens and character n-grams (1-3) to handle both space-separated
    words and continuous script text (e.g. Thai) cleanly in pure Python.
    """
    cleaned = text.lower().strip()
    words = re.findall(r"\w+", cleaned)
    tokens: list[str] = list(words)

    # Add character 2-grams and 3-grams within words to handle continuous/subword patterns
    for w in words:
        for n in (2, 3):
            if len(w) >= n:
                tokens.extend(w[i : i + n] for i in range(len(w) - n + 1))

    return tokens


def _compute_cosine_similarity(vec1: dict[str, float], vec2: dict[str, float]) -> float:
    """Compute cosine similarity combined with query coverage between two sparse term vectors."""
    common_terms = set(vec1.keys()) & set(vec2.keys())
    if not common_terms:
        return 0.0

    dot_product = sum(vec1[t] * vec2[t] for t in common_terms)
    norm1 = math.sqrt(sum(v * v for v in vec1.values()))
    norm2 = math.sqrt(sum(v * v for v in vec2.values()))

    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0

    cosine = dot_product / (norm1 * norm2)
    coverage = dot_product / (norm1 * norm1)
    combined = 0.5 * cosine + 0.5 * min(1.0, coverage)
    return max(0.0, min(1.0, combined))


def search_products_embeddings(
    text: str,
    products: list[Inventory],
    threshold: float = 0.8,
) -> EmbeddingSearchResult | None:
    """
    In-memory TF-IDF cosine similarity search over product names and categories.
    Stub implementation for Phase 5 semantic search.
    Returns EmbeddingSearchResult if top match confidence >= threshold, else None.
    """
    if not text or not products:
        return None

    qty, query_without_qty = extract_quantity(text)
    size, query_cleaned = extract_size(query_without_qty)

    query_tokens = _tokenize(query_cleaned)
    if not query_tokens:
        return None

    query_tf = Counter(query_tokens)

    # Prepare document corpus
    active_products = [p for p in products if p.active]
    if not active_products:
        return None

    # Track tokens for product name and name+category
    doc_entries: list[tuple[Inventory, list[str], list[str]]] = []
    all_doc_tokens: list[list[str]] = []
    for p in active_products:
        name_toks = _tokenize(p.name)
        full_toks = _tokenize(f"{p.name} {p.category or ''}".strip())
        doc_entries.append((p, name_toks, full_toks))
        all_doc_tokens.append(name_toks)
        if p.category:
            all_doc_tokens.append(full_toks)

    n_docs = len(all_doc_tokens)

    # Compute document frequency (DF) for IDF calculation
    df: Counter[str] = Counter()
    for tokens in all_doc_tokens:
        unique_tokens = set(tokens)
        for t in unique_tokens:
            df[t] += 1

    # Compute TF-IDF vector for query
    query_vec: dict[str, float] = {}
    for term, count in query_tf.items():
        doc_freq = df.get(term, 0)
        idf = math.log((1 + n_docs) / (1 + doc_freq)) + 1.0
        query_vec[term] = count * idf

    def _to_tfidf_vec(tokens: list[str]) -> dict[str, float]:
        tf = Counter(tokens)
        vec: dict[str, float] = {}
        for term, count in tf.items():
            doc_freq = df.get(term, 0)
            idf = math.log((1 + n_docs) / (1 + doc_freq)) + 1.0
            vec[term] = count * idf
        return vec

    best_product: Inventory | None = None
    best_score: float = 0.0

    for product, name_toks, full_toks in doc_entries:
        score_name = _compute_cosine_similarity(query_vec, _to_tfidf_vec(name_toks))
        score_full = (
            _compute_cosine_similarity(query_vec, _to_tfidf_vec(full_toks))
            if product.category
            else 0.0
        )
        score = max(score_name, score_full)
        if score > best_score:
            best_score = score
            best_product = product

    if best_product and best_score >= threshold:
        has_sizes = product_has_sizes(best_product)
        final_size = (
            size
            if (size and (not has_sizes or size in has_sizes))
            else (has_sizes[0] if has_sizes and not size else size)
        )

        return EmbeddingSearchResult(
            product=best_product,
            sku=best_product.sku,
            name=best_product.name,
            qty=qty,
            size=final_size,
            confidence=best_score,
        )

    return None
