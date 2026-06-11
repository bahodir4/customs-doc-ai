"""Schema registry for all supported customs document types.

Single entry point: `validate_and_parse(doc_type, raw_dict)` runs the
right Pydantic model and returns (errors, cleaned_dict). On failure the
original dict is returned alongside the errors so the correction UI can
still display what the LLM produced.
"""
from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, ValidationError

from core.schemas.awb import AWBSchema
from core.schemas.cmr import CMRSchema
from core.schemas.common import BankDetails, LineItem, Party
from core.schemas.gtd import GTDLineItem, GTDSchema
from core.schemas.invoice import InvoiceSchema
from core.schemas.packing_list import PackageItem, PackingListSchema

DOC_TYPES: Final[tuple[str, ...]] = (
    "invoice",
    "awb",
    "gtd",
    "cmr",
    "packing_list",
)

_SCHEMA_MAP: Final[dict[str, type[BaseModel]]] = {
    "invoice": InvoiceSchema,
    "awb": AWBSchema,
    "gtd": GTDSchema,
    "cmr": CMRSchema,
    "packing_list": PackingListSchema,
}


def get_schema(doc_type: str) -> type[BaseModel]:
    """Return the Pydantic model class for the given doc type."""
    schema = _SCHEMA_MAP.get(doc_type)
    if schema is None:
        raise ValueError(
            f"No schema for doc_type {doc_type!r}. Valid: {list(_SCHEMA_MAP)}"
        )
    return schema


def validate_and_parse(
    doc_type: str, data: dict[str, Any]
) -> tuple[list[str], dict[str, Any]]:
    """Validate raw extracted data; return (errors, cleaned_dict).

    On success: errors is empty, cleaned_dict is the schema's `model_dump`.
    On failure: errors lists the validation issues, cleaned_dict is the
    original data so callers can still display it.
    """
    schema = _SCHEMA_MAP.get(doc_type)
    if schema is None:
        return [f"No schema for doc_type {doc_type!r}"], data
    try:
        instance = schema(**data)
        return [], instance.model_dump(mode="json")
    except ValidationError as exc:
        return [_format_error(err) for err in exc.errors()], data


def _format_error(err: dict[str, Any]) -> str:
    loc = ".".join(str(p) for p in err.get("loc", ()))
    msg = err.get("msg", "validation error")
    return f"{loc}: {msg}" if loc else msg


__all__ = [
    "AWBSchema",
    "BankDetails",
    "CMRSchema",
    "DOC_TYPES",
    "GTDLineItem",
    "GTDSchema",
    "InvoiceSchema",
    "LineItem",
    "PackageItem",
    "PackingListSchema",
    "Party",
    "get_schema",
    "validate_and_parse",
]
