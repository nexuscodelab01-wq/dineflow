"""Schemas for restaurant-defined allergens and dish types."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

LabelKind = Literal["allergen", "dish_type"]


def _clean(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("Enter a name")
    return cleaned


class LabelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: LabelKind
    code: str
    label: str
    sort_order: int
    # How many dishes carry it (only filled in for the admin list, so the delete confirmation can say so).
    item_count: int = 0


class LabelCreate(BaseModel):
    kind: LabelKind
    label: str = Field(min_length=1, max_length=60)

    _clean_label = field_validator("label")(_clean)


class LabelUpdate(BaseModel):
    label: str = Field(min_length=1, max_length=60)

    _clean_label = field_validator("label")(_clean)
