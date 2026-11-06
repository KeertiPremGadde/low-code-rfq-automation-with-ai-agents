"""Pydantic models: the structure the LLM must return, and the API request."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EquipmentType = Literal[
    "heavy-duty gas turbine",
    "aeroderivative gas turbine",
    "compressor",
    "generator",
    "combustion parts",
]
ServiceType = Literal["inspection", "overhaul", "upgrade", "spare parts"]
# Details a bid manager needs. Anything absent from the RFQ goes into missing_info.
FieldName = Literal[
    "customer", "site", "equipment_type", "service_type", "due_date",
    "operating_hours", "serial_number", "outage_window",
]


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer: str | None = Field(description="Company that sent the RFQ, or null if not stated")
    site: str | None = Field(description="Plant or site where the work happens, or null if not stated")
    equipment_type: EquipmentType | None
    service_type: ServiceType | None
    due_date: date | None = Field(description="Quotation deadline as ISO date YYYY-MM-DD, or null if not stated")
    scope_summary: str | None = Field(description="One or two sentences on the work requested; no personal data")
    missing_info: list[FieldName] = Field(description="Names of every field above that the RFQ text does not state")


class ExtractRequest(BaseModel):
    message_id: str


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
