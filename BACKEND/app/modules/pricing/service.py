"""Pricing settings (PRC-05, PRD «قیمت و مالیات» ✓, ADR-027, ADR-033)."""

from __future__ import annotations

import logging
from typing import Any, Final

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.db.models import PricingSetting
from app.modules.auth.service import CurrentUser
from app.modules.pricing.repository import PricingSettingsRepository
from app.modules.pricing.schemas import (
    EDITABLE_FIELDS,
    PricingSettingsResponse,
    UpdatePricingSettingsRequest,
)
from app.shared.audit import record_audit

logger = logging.getLogger(__name__)

SETTINGS_PERMISSION: Final = "pricing_settings:update"


def _not_found() -> NotFoundError:
    return NotFoundError(message="Pricing settings not found")


def _snapshot(setting: PricingSetting) -> dict[str, Any]:
    return {field: getattr(setting, field) for field in (*EDITABLE_FIELDS, "version")}


def _response(setting: PricingSetting) -> PricingSettingsResponse:
    return PricingSettingsResponse.model_validate(setting, from_attributes=True)


class PricingSettingsService:
    def __init__(self, session: AsyncSession, repository: PricingSettingsRepository) -> None:
        self._session = session
        self._repository = repository

    async def get(self) -> PricingSettingsResponse:
        async with self._session.begin():
            setting = await self._repository.get()
            if setting is None:
                raise _not_found()
            return _response(setting)

    async def update(
        self,
        actor: CurrentUser,
        payload: UpdatePricingSettingsRequest,
        audit_request: Request | None,
    ) -> PricingSettingsResponse:
        """Change the settings; an unchanged body is a 200 without audit or version bump."""
        async with self._session.begin():
            setting = await self._repository.lock()
            if setting is None:
                raise _not_found()
            changes = {
                field: getattr(payload, field)
                for field in sorted(payload.model_fields_set)
                if getattr(payload, field) != getattr(setting, field)
            }
            if not changes:
                return _response(setting)
            before = _snapshot(setting)
            for field, value in changes.items():
                setattr(setting, field, value)
            setting.version += 1
            setting.updated_by = actor.id
            await self._session.flush()
            await record_audit(
                self._session,
                actor_id=actor.id,
                action="pricing.settings_updated",
                entity_type="pricing_settings",
                entity_id=setting.id,
                before=before,
                after=_snapshot(setting),
                request=audit_request,
            )
            # updated_at is set by the ORM onupdate on flush; refresh reads it back.
            await self._session.refresh(setting)
            response = _response(setting)
        logger.info(
            "pricing.settings_updated",
            extra={"fields": sorted(changes), "version": response.version},
        )
        return response
