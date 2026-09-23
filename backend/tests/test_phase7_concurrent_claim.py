import inspect
import threading
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import func, select

from app.models.payment import ConsumedPaymentClaim
from app.services.verification_service import claim_payment
from tests.conftest import TestingSessionLocal


def test_concurrent_threads_inserting_same_claim_key_exactly_one_succeeds():
    """
    CRITICAL HUMAN REVIEWER ITEM 1 (TEST_PLAN.md Phase 7, v1_buildable_spec.md §13, §20):
    Concurrent threads inserting the same claim_key:
    - Exactly one succeeds via ON CONFLICT DO NOTHING RETURNING id.
    - Zero SELECT queries before INSERT.
    - Real threads (not sequential calls) hitting the same claim_key simultaneously on PostgreSQL.
    - Exactly one DB row is created in consumed_payment_claims.
    """
    claim_key = "ref:CONCURRENT-TEST-777"
    num_threads = 4
    barrier = threading.Barrier(num_threads)
    results: list[int | None] = []
    lock = threading.Lock()

    def attempt_claim(worker_id: int) -> None:
        order_id = f"ORD-CLAIM-{worker_id}"
        # Synchronize all threads so they strike the DB at the exact same instant
        barrier.wait()
        with TestingSessionLocal() as session:
            try:
                claim_id = claim_payment(
                    db=session,
                    claim_key=claim_key,
                    order_id=order_id,
                    shop_id="default",
                    claim_type="ref",
                    state="PENDING",
                )
                with lock:
                    results.append(claim_id)
            except Exception:
                with lock:
                    results.append(None)

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(attempt_claim, i) for i in range(num_threads)]
        for f in futures:
            f.result()

    # Assert exactly one thread succeeded in inserting the claim
    successful_claims = [r for r in results if r is not None]
    failed_claims = [r for r in results if r is None]

    assert len(successful_claims) == 1, (
        f"Expected exactly 1 successful claim, but got {len(successful_claims)}. Results: {results}"
    )
    assert len(failed_claims) == num_threads - 1

    # Assert exactly 1 row in PostgreSQL consumed_payment_claims table
    with TestingSessionLocal() as session:
        count_stmt = select(func.count(ConsumedPaymentClaim.id)).where(
            ConsumedPaymentClaim.claim_key == claim_key
        )
        row_count = session.execute(count_stmt).scalar_one()
        assert row_count == 1, f"Expected exactly 1 row in DB, got {row_count}"

        claim = session.execute(
            select(ConsumedPaymentClaim).where(ConsumedPaymentClaim.claim_key == claim_key)
        ).scalar_one()
        assert claim.state == "PENDING"
        assert claim.id == successful_claims[0]


def test_claim_payment_implementation_has_zero_select_before_insert():
    """
    CRITICAL REQUIREMENT 1: Code-level verification that claim_payment
    contains zero SELECT statements checking for claim existence.
    Deduplication must be enforced entirely by the atomic INSERT ON CONFLICT.
    """
    source = inspect.getsource(claim_payment)

    # Must contain atomic INSERT ... ON CONFLICT
    assert "INSERT INTO consumed_payment_claims" in source
    assert "ON CONFLICT (claim_key) DO NOTHING" in source
    assert "RETURNING id" in source

    # Must NOT contain SELECT before INSERT
    insert_pos = source.find("INSERT INTO consumed_payment_claims")
    code_before_insert = source[:insert_pos]

    assert "select(" not in code_before_insert.lower()
    assert "SELECT" not in code_before_insert
    assert "session.query" not in code_before_insert
