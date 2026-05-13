"""Validate modifier option picks for a menu item and compute per-unit price add-on."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from django.core.exceptions import ValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError

from .models import MenuItem, MenuItemModifierGroup, ModifierOption


def resolve_modifier_selection_for_menu_item(
    *,
    menu_item: MenuItem,
    option_ids: list[UUID] | None,
) -> tuple[Decimal, list[dict]]:
    """
    Return (sum of per-unit price deltas, snapshot for persistence).
    Raises ValidationError when counts violate group min/max or unknown options.
    """
    ids = [x for x in (option_ids or []) if x]

    links = list(
        MenuItemModifierGroup.objects.filter(menu_item=menu_item).select_related("group")
    )
    if not links:
        if ids:
            raise ValidationError("This item does not support modifiers.")
        return Decimal("0"), []

    allowed_group_ids = {l.group_id for l in links}

    if not ids:
        for link in links:
            g = link.group
            if g.min_selections > 0:
                raise ValidationError(
                    f'Group "{g.name}" requires at least {g.min_selections} selection(s).'
                )
        return Decimal("0"), []

    options = list(
        ModifierOption.objects.filter(
            id__in=ids,
            group_id__in=allowed_group_ids,
            is_active=True,
        ).select_related("group")
    )
    if len(options) != len(set(ids)):
        raise ValidationError("Unknown or inactive modifier option for this item.")

    by_group: dict = defaultdict(list)
    for o in options:
        by_group[o.group_id].append(o)

    for link in links:
        g = link.group
        picked = by_group.get(g.id, [])
        n = len(picked)
        min_sel = g.min_selections
        max_sel = g.max_selections if g.max_selections is not None else 999
        if n < min_sel:
            raise ValidationError(
                f'Group "{g.name}" requires at least {min_sel} selection(s); {n} given.'
            )
        if n > max_sel:
            raise ValidationError(
                f'Group "{g.name}" allows at most {max_sel} selection(s); {n} given.'
            )

    per_unit_extra = sum((o.price_delta for o in options), start=Decimal("0"))
    snapshot = [
        {
            "id": str(o.id),
            "group": o.group.name,
            "name": o.name,
            "price_delta": str(o.price_delta),
        }
        for o in sorted(options, key=lambda x: (x.group.name, x.sort_order, x.name))
    ]
    return per_unit_extra, snapshot


def resolve_modifier_selection_drfsafe(*args, **kwargs) -> tuple[Decimal, list[dict]]:
    try:
        return resolve_modifier_selection_for_menu_item(*args, **kwargs)
    except ValidationError as exc:
        if hasattr(exc, "error_dict"):
            raise DRFValidationError(exc.error_dict) from exc
        msgs = getattr(exc, "messages", None) or [str(exc)]
        raise DRFValidationError(msgs if len(msgs) > 1 else msgs[0]) from exc
