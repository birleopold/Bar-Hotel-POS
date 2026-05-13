"""Small DRF helpers to keep ``OrderViewSet`` readable."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from rest_framework import status
from rest_framework.response import Response

from apps.catalog.models import MenuItem

from .services import menu_item_available_at_outlet

if TYPE_CHECKING:
    from apps.pos.models import Order


def idempotency_header_or_error(request) -> tuple[str | None, Response | None]:
    raw = request.headers.get("Idempotency-Key") or request.headers.get("idempotency-key")
    if not raw or not str(raw).strip():
        return None, Response(
            {
                "error": {
                    "code": "idempotency_required",
                    "message": "Send non-empty header Idempotency-Key.",
                }
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    return str(raw).strip(), None


def order_line_or_error(order: Order, line_uuid) -> tuple[object | None, Response | None]:
    from .models import OrderLine

    line = OrderLine.objects.filter(id=line_uuid, order_id=order.id).first()
    if line is None:
        return None, Response(
            {"error": {"code": "invalid_line", "message": "Line not on this order."}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return line, None


def menu_item_for_order_or_error(
    *,
    tenant_id,
    order: Order,
    menu_item_id: uuid.UUID,
) -> tuple[MenuItem | None, Response | None]:
    item = MenuItem.objects.filter(
        id=menu_item_id,
        tenant_id=tenant_id,
        is_active=True,
    ).first()
    if item is None:
        return None, Response(
            {"error": {"code": "invalid_item", "message": "Unknown menu item."}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not menu_item_available_at_outlet(item, order.outlet_id):
        return None, Response(
            {"error": {"code": "item_unavailable", "message": "Item not available at this outlet."}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return item, None


def promotion_for_order_or_error(*, tenant_id, promotion_id: uuid.UUID):
    from apps.catalog.models import Promotion

    promo = Promotion.objects.filter(id=promotion_id, tenant_id=tenant_id).first()
    if promo is None:
        return None, Response(
            {"error": {"code": "invalid_promotion", "message": "Promotion not found."}},
            status=status.HTTP_404_NOT_FOUND,
        )
    return promo, None
