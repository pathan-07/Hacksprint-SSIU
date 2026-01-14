from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class Intent(str, Enum):
    add_udhaar = "add_udhaar"
    record_payment = "record_payment"
    undo_last = "undo_last"
    get_summary = "get_summary"
    get_customer_total = "get_customer_total"


class IntentResult(BaseModel):
    intent: Intent
    customer_name: str = Field(default="")
    amount: float | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class PendingAction(BaseModel):
    action_type: str
    action_json: dict
