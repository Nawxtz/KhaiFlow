import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.address_book import AddressBook
from app.schemas.address_book import (
    AddressBookCreate,
    AddressBookDeleteResponse,
    AddressBookRead,
)
from app.services.pdpa_service import has_pdpa_consent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/address-book", tags=["address-book"])


@router.get("", response_model=list[AddressBookRead])
def list_address_book(
    line_user_id: str | None = Query(None, description="Filter by LINE user ID"),
    shop_id: str | None = Query(None, description="Filter by shop ID"),
    db: Session = Depends(get_db),
) -> Any:
    """List address book entries, optionally filtered by user ID and shop ID."""
    stmt = select(AddressBook).order_by(AddressBook.created_at.desc())
    if line_user_id:
        stmt = stmt.where(AddressBook.line_user_id == line_user_id)
    if shop_id:
        stmt = stmt.where(AddressBook.shop_id == shop_id)
    return list(db.execute(stmt).scalars().all())


@router.get("/{address_id}", response_model=AddressBookRead)
def get_address_entry(
    address_id: int,
    shop_id: str | None = Query(None, description="Filter by shop ID"),
    db: Session = Depends(get_db),
) -> Any:
    """Get a single address book entry by ID."""
    stmt = select(AddressBook).where(AddressBook.id == address_id)
    if shop_id:
        stmt = stmt.where(AddressBook.shop_id == shop_id)
    entry = db.execute(stmt).scalars().first()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Address entry '{address_id}' not found",
        )
    return entry


@router.post("", response_model=AddressBookRead, status_code=status.HTTP_201_CREATED)
def create_address_entry(
    payload: AddressBookCreate,
    db: Session = Depends(get_db),
) -> Any:
    """Create a new address book entry."""
    if not has_pdpa_consent(db, payload.line_user_id, payload.shop_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="PDPA consent required before creating address book entry",
        )
    if payload.is_default:
        # Clear default flag on existing addresses for this user
        existing_defaults = (
            db.query(AddressBook)
            .filter(
                AddressBook.line_user_id == payload.line_user_id,
                AddressBook.is_default == True,  # noqa: E712
            )
            .all()
        )
        for existing in existing_defaults:
            existing.is_default = False

    entry = AddressBook(
        shop_id=payload.shop_id,
        line_user_id=payload.line_user_id,
        label=payload.label,
        receiver_name=payload.receiver_name,
        phone=payload.phone,
        address_json=payload.address_json,
        is_default=payload.is_default,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{address_id}", response_model=AddressBookDeleteResponse)
def delete_address_entry(
    address_id: int,
    shop_id: str | None = Query(None, description="Filter by shop ID"),
    db: Session = Depends(get_db),
) -> Any:
    """Delete an address book entry by path ID."""
    stmt = select(AddressBook).where(AddressBook.id == address_id)
    if shop_id:
        stmt = stmt.where(AddressBook.shop_id == shop_id)
    entry = db.execute(stmt).scalars().first()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Address entry '{address_id}' not found",
        )
    db.delete(entry)
    db.commit()
    return AddressBookDeleteResponse(status="deleted", id=address_id)


@router.delete("", response_model=AddressBookDeleteResponse)
def delete_address_by_query(
    id: int = Query(..., description="Address entry ID to delete"),
    shop_id: str | None = Query(None, description="Filter by shop ID"),
    db: Session = Depends(get_db),
) -> Any:
    """Delete an address book entry by query parameter ID."""
    return delete_address_entry(address_id=id, shop_id=shop_id, db=db)
