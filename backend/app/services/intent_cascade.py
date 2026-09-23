import logging
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.inventory import Inventory
from app.schemas.order import OrderDraftIntent
from app.services.embeddings_search import search_products_embeddings
from app.services.llm_router import extract_intent_llm
from app.services.rules_engine import match_product_rules

logger = logging.getLogger(__name__)


def get_active_inventory_products(db: Session, shop_id: str | None = None) -> list[Inventory]:
    """Retrieve all active inventory items for the given shop or default shop."""
    stmt = select(Inventory).where(Inventory.active == True)  # noqa: E712
    if shop_id:
        stmt = stmt.where(or_(Inventory.shop_id == shop_id, Inventory.shop_id.is_(None)))
    return list(db.execute(stmt).scalars().all())


def extract_order_intent_with_stage(
    text: str,
    db: Session,
    shop_id: str | None = None,
    lang: str = "th",
) -> tuple[OrderDraftIntent | None, str | None]:
    """
    3-stage cascade: Rules -> Embeddings -> LLM extractor.
    Returns (OrderDraftIntent, stage_name) or (None, None).
    """
    if not text or not text.strip():
        return None, None

    products = get_active_inventory_products(db, shop_id=shop_id)
    if not products:
        logger.info("No active products in inventory for shop_id: %s", shop_id)
        return None, None

    threshold = float(getattr(settings, "LLM_ESCALATE_CONFIDENCE", 0.8))
    llm_enabled = bool(getattr(settings, "LLM_ENABLED", True))

    # Stage 1: Rules Engine (RapidFuzz string matching)
    rule_res = match_product_rules(text, products, threshold=threshold)
    if rule_res and rule_res.confidence >= threshold:
        logger.info(
            "Cascade Stage 1 (rules) matched %s (confidence: %.2f)",
            rule_res.sku,
            rule_res.confidence,
        )
        prod = rule_res.product
        unit_price = Decimal(prod.price)
        line_total = Decimal(rule_res.qty) * unit_price
        intent = OrderDraftIntent(
            sku=prod.sku,
            name=prod.name,
            qty=rule_res.qty,
            size=rule_res.size,
            unit_price=unit_price,
            line_total=line_total,
        )
        return intent, "rules"

    # Stage 2: Embeddings Search (TF-IDF semantic cosine similarity)
    emb_res = search_products_embeddings(text, products, threshold=threshold)
    if emb_res and emb_res.confidence >= threshold:
        logger.info(
            "Cascade Stage 2 (embeddings) matched %s (confidence: %.2f)",
            emb_res.sku,
            emb_res.confidence,
        )
        prod = emb_res.product
        unit_price = Decimal(prod.price)
        line_total = Decimal(emb_res.qty) * unit_price
        intent = OrderDraftIntent(
            sku=prod.sku,
            name=prod.name,
            qty=emb_res.qty,
            size=emb_res.size,
            unit_price=unit_price,
            line_total=line_total,
        )
        return intent, "embeddings"

    # Stage 3: LLM Extractor (OpenRouter)
    if not llm_enabled:
        logger.info("No-LLM mode active (llm_enabled=False). Stopping cascade at embeddings.")
        return None, None

    llm_res = extract_intent_llm(text, products, threshold=threshold)
    if llm_res and llm_res.confidence >= threshold and llm_res.sku:
        logger.info(
            "Cascade Stage 3 (LLM) matched %s (confidence: %.2f)", llm_res.sku, llm_res.confidence
        )
        matched_prod = next((p for p in products if p.sku == llm_res.sku), None)
        if not matched_prod:
            logger.warning("LLM matched SKU %s not found in active inventory", llm_res.sku)
            return None, "llm"

        unit_price = Decimal(matched_prod.price)
        line_total = Decimal(llm_res.qty) * unit_price
        intent = OrderDraftIntent(
            sku=matched_prod.sku,
            name=matched_prod.name,
            qty=llm_res.qty,
            size=llm_res.size,
            unit_price=unit_price,
            line_total=line_total,
        )
        return intent, "llm"

    # All cascade stages failed or had low confidence
    logger.info("Cascade failed to confidently match intent for text: %s", text[:50])
    return None, None


def extract_order_intent(
    text: str,
    db: Session,
    shop_id: str | None = None,
    lang: str = "th",
) -> OrderDraftIntent | None:
    """
    Extract order intent through the 3-stage cascade: rules -> embeddings -> LLM.
    Returns OrderDraftIntent if confident match found, else None.
    """
    intent, _ = extract_order_intent_with_stage(text, db, shop_id=shop_id, lang=lang)
    return intent
