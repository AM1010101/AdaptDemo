from pydantic import BaseModel
from typing import Optional

class RawProductScrapeData(BaseModel):
    make: str
    model: str
    storage_capacity: str
    grade: str
    colour: str
    ce_mark: Optional[bool] = None
    partial_vat: bool
    purchase_price: float
    trade_in_price: Optional[float] = None
    stock_count: int

class RawProductScrape(BaseModel):
    source_id: str
    make: str
    model: str
    storage_capacity: str
    grade: str
    colour: str
    ce_mark: Optional[bool] = None
    partial_vat: bool
    purchase_price: float
    trade_in_price: Optional[float] = None
    stock_count: int
    meta_data: str  # JSON string
    scrape_instance: Optional[str] = None

class RawProductScrapeMeta(BaseModel):
    source_id: str
    meta_data: str  # JSON string
    scrape_instance: Optional[str] = None
