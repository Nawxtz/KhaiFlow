from pydantic import BaseModel, ConfigDict, Field


class InventoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sku: str
    shop_id: str | None = None
    name: str
    category: str | None = None
    price: float = Field(..., description="Item price in THB")
    image_url: str | None = None
    stock: int = Field(..., ge=0, description="Physical stock")
    reserved: int = Field(0, ge=0, description="Held reservations")
    available_stock: int = Field(..., ge=0, description="Available stock = stock - reserved")
    active: bool = True
    version: int = 1


class IngestSummary(BaseModel):
    rows_total: int = 0
    rows_valid: int = 0
    rows_skipped: int = 0
    rows_inserted: int = 0
    rows_updated: int = 0
    rows_unchanged: int = 0
    skipped_reasons: list[str] = Field(default_factory=list)
