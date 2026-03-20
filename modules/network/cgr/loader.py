from __future__ import annotations

import json
import logging
from random import randint
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator

from .exceptions import ContactPlanFormatError, ContactPlanValidationError
from .models import Contact

logger = logging.getLogger(__name__)


class ContactPlanEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    start: int
    end: int
    frm: int = Field(alias="from")
    to: int
    rate: int
    owlt: int = 0

    @model_validator(mode="after")
    def validate_business_rules(self) -> ContactPlanEntry:
        if self.end <= self.start:
            raise ValueError("'end' must be greater than 'start'")
        if self.rate <= 0:
            raise ValueError("'rate' must be greater than 0")
        if self.frm == self.to:
            raise ValueError("'from' and 'to' must be different")
        if self.owlt < 0:
            raise ValueError("'owlt' must be greater than or equal to 0")
        return self


class ContactPlanDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contacts: list[ContactPlanEntry]


def _parse_contacts_payload(payload: Any) -> list[ContactPlanEntry]:
    try:
        if isinstance(payload, dict):
            return ContactPlanDocument.model_validate(payload).contacts
        if isinstance(payload, list):
            return TypeAdapter(list[ContactPlanEntry]).validate_python(payload)
        raise ContactPlanFormatError(
            "Invalid contact plan JSON format: expected a list or an object with 'contacts'."
        )
    except ValidationError as exc:
        raise ContactPlanValidationError(f"Invalid contact plan JSON: {exc}") from exc


# load contact plan from JSON format.
# Accepted schemas:
# 1) {"contacts": [{"start":0,"end":10,"from":1,"to":2,"rate":1,"owlt":1}, ...]}
# 2) [{"start":0,"end":10,"from":1,"to":2,"rate":1,"owlt":1}, ...]
def cp_load(file_name: str, max_contacts: int | None = None) -> list[Contact]:
    with open(file_name, "r", encoding="utf-8") as cf:
        payload = json.load(cf)

    contacts = _parse_contacts_payload(payload)

    contact_plan: list[Contact] = []
    for contact in contacts:
        contact_plan.append(
            Contact(
                start=contact.start,
                end=contact.end,
                frm=contact.frm,
                to=contact.to,
                rate=contact.rate,
                owlt=contact.owlt,
            )
        )
        if max_contacts is not None and len(contact_plan) >= max_contacts:
            break

    logger.info("cp.load | file=%s contacts=%d", file_name, len(contact_plan))
    return contact_plan


# construct a random contact plan
def cp_random(max_contacts: int, max_nodes: int) -> list[Contact]:
    contact_plan: list[Contact] = []
    for _ in range(max_contacts):
        start = randint(0, 999)
        end = start + randint(1, 100)
        frm = randint(1, max_nodes)
        to = randint(1, max_nodes)
        while to == frm:
            to = randint(1, max_nodes)
        rate = 1
        owlt = 1
        contact_plan.append(Contact(start=start, end=end, frm=frm, to=to, rate=rate, owlt=owlt))
    return contact_plan
