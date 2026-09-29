import json
from decimal import Decimal

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.access.outlets import outlet_belongs_to_membership
from apps.accounts.models import Membership
from apps.pos.models import Order
from apps.tenants.models import Tenant

from .orders import (
    add_line_to_open_order,
    create_order_with_lines,
    default_currency_for_tenant,
    normalize_supermarket_quantity,
    resolve_folio_for_order,
    resolve_order_create,
    resolve_table,
)
from .payments import record_order_payment


def _payload_json_safe(payload: dict) -> dict:
    """Normalize DRF validated_data (UUID, Decimal, …) for ``JSONField`` storage."""
    return json.loads(json.dumps(payload, cls=DjangoJSONEncoder))


def _finalize_order_payment(*, obj, tenant_id, outlet, user, payload: dict):
    from apps.pos.models import OfflineQueueStatus

    oid = payload.get("order_id")
    idem = (payload.get("idempotency_key") or "").strip()
    amount = Decimal(str(payload.get("amount", "0")))
    method = payload.get("method")
    if not oid or not idem or not method:
        raise ValidationError("payload requires order_id, idempotency_key, method, amount.")
    order = Order.objects.get(id=oid, tenant_id=tenant_id, outlet_id=outlet.id)
    payment, _replay = record_order_payment(
        order=order,
        user=user,
        amount=amount,
        method=method,
        idempotency_key=idem,
    )
    obj.status = OfflineQueueStatus.APPLIED
    obj.applied_payment_id = payment.id
    obj.applied_order_id = None
    obj.error_message = ""
    obj.save(
        update_fields=["status", "applied_payment_id", "applied_order_id", "error_message", "updated_at"]
    )


def _finalize_order_create(
    *,
    obj,
    tenant_id,
    membership: Membership,
    outlet,
    user,
    payload: dict,
):
    from apps.pos.models import OfflineQueueStatus

    tenant = Tenant.objects.get(pk=tenant_id)
    lines_in = []
    for row in payload["lines"]:
        entry = {"menu_item": row["menu_item"], "quantity": row["quantity"]}
        mods = row.get("modifier_option_ids")
        if mods:
            entry["modifier_option_ids"] = list(mods)
        lines_in.append(entry)
    _, resolved = resolve_order_create(
        tenant,
        membership,
        outlet_id=outlet.id,
        lines=lines_in,
    )
    for row in resolved:
        q = row["quantity"]
        if not isinstance(q, Decimal):
            q = Decimal(str(q))
        row["quantity"] = normalize_supermarket_quantity(menu_item=row["menu_item"], quantity=q)

    table = resolve_table(tenant_id, outlet.id, payload.get("table"))
    folio = resolve_folio_for_order(tenant_id, membership, outlet, payload.get("folio"))
    currency = (payload.get("currency") or "").strip() or default_currency_for_tenant(tenant)

    order = create_order_with_lines(
        tenant_id=tenant_id,
        outlet=outlet,
        created_by=user,
        currency=currency,
        table_label=(payload.get("table_label") or "")[:64],
        lines=resolved,
        table=table,
        folio=folio,
    )
    obj.status = OfflineQueueStatus.APPLIED
    obj.applied_order_id = order.id
    obj.applied_payment_id = None
    obj.error_message = ""
    obj.save(
        update_fields=["status", "applied_order_id", "applied_payment_id", "error_message", "updated_at"]
    )


def _finalize_order_add_lines(
    *,
    obj,
    tenant_id,
    membership: Membership,
    outlet,
    user,
    payload: dict,
):
    from apps.pos.models import OfflineQueueStatus

    order = Order.objects.get(id=payload["order_id"], tenant_id=tenant_id, outlet_id=outlet.id)
    tenant = Tenant.objects.get(pk=tenant_id)
    lines_in = []
    for row in payload["lines"]:
        entry = {"menu_item": row["menu_item"], "quantity": row["quantity"]}
        mods = row.get("modifier_option_ids")
        if mods:
            entry["modifier_option_ids"] = list(mods)
        lines_in.append(entry)
    _, resolved = resolve_order_create(
        tenant,
        membership,
        outlet_id=outlet.id,
        lines=lines_in,
    )
    for row in resolved:
        q = row["quantity"]
        if not isinstance(q, Decimal):
            q = Decimal(str(q))
        qty = normalize_supermarket_quantity(menu_item=row["menu_item"], quantity=q)
        add_line_to_open_order(
            order=order,
            menu_item=row["menu_item"],
            quantity=qty,
            user=user,
            modifier_option_ids=row.get("modifier_option_ids") or [],
        )
    obj.status = OfflineQueueStatus.APPLIED
    obj.applied_order_id = order.id
    obj.applied_payment_id = None
    obj.error_message = ""
    obj.save(
        update_fields=["status", "applied_order_id", "applied_payment_id", "error_message", "updated_at"]
    )


@transaction.atomic
def record_catalog_stale_rejection(
    *,
    tenant_id,
    outlet,
    client_mutation_id: str,
    operation_type: str,
    payload: dict,
    error_payload: dict,
) -> None:
    """
    Persist a FAILED queue row when the API returns 409 ``catalog_stale``.

    Lets staff see conflicts in ``/staff/pos/offline-queue/`` even though the mutation
    was never applied. Skips if the mutation already reached APPLIED (replay semantics).
    """
    from apps.pos.models import OfflineQueuedOperation, OfflineQueueStatus

    cid = (client_mutation_id or "").strip()[:128]
    if not cid:
        return
    if OfflineQueuedOperation.objects.filter(
        tenant_id=tenant_id,
        client_mutation_id=cid,
        status=OfflineQueueStatus.APPLIED,
    ).exists():
        return

    payload_safe = _payload_json_safe(dict(payload))
    err = error_payload.get("error") if isinstance(error_payload, dict) else {}
    if isinstance(err, dict):
        server_cv = err.get("server_catalog_version", "")
        as_of = err.get("as_of", "")
        msg = err.get("message", "")
        error_message = f"catalog_stale: server_catalog_version={server_cv} as_of={as_of}. {msg}"[:2000]
    else:
        error_message = "catalog_stale"

    OfflineQueuedOperation.objects.update_or_create(
        tenant_id=tenant_id,
        client_mutation_id=cid,
        defaults={
            "outlet": outlet,
            "operation_type": operation_type,
            "payload": payload_safe,
            "status": OfflineQueueStatus.FAILED,
            "error_message": error_message,
        },
    )


@transaction.atomic
def process_offline_queue_entry(
    *,
    tenant_id,
    membership: Membership,
    outlet,
    user,
    client_mutation_id: str,
    operation_type: str,
    payload: dict,
):
    from apps.pos.models import OfflineQueuedOperation, OfflineQueueStatus

    if not outlet_belongs_to_membership(membership, outlet.id):
        raise ValidationError({"outlet": "You cannot sync for this outlet."})

    payload = _payload_json_safe(dict(payload))

    obj, _created = OfflineQueuedOperation.objects.get_or_create(
        tenant_id=tenant_id,
        client_mutation_id=client_mutation_id.strip()[:128],
        defaults={
            "outlet": outlet,
            "operation_type": operation_type,
            "payload": payload,
            "status": OfflineQueueStatus.PENDING,
        },
    )
    obj = OfflineQueuedOperation.objects.select_for_update().get(pk=obj.pk)
    if obj.status == OfflineQueueStatus.APPLIED and (
        obj.outlet_id != outlet.id or obj.operation_type != operation_type or obj.payload != payload
    ):
        raise ValidationError({"client_mutation_id": "This mutation ID was already used for a different operation."})
    if obj.status == OfflineQueueStatus.APPLIED:
        return obj, True

    obj.outlet = outlet
    obj.operation_type = operation_type
    obj.payload = payload
    obj.status = OfflineQueueStatus.PENDING
    obj.error_message = ""
    obj.save(
        update_fields=[
            "outlet",
            "operation_type",
            "payload",
            "status",
            "error_message",
            "updated_at",
        ]
    )

    if operation_type not in {"order_payment", "order_create", "order_add_lines"}:
        obj.status = OfflineQueueStatus.FAILED
        obj.error_message = f"Unsupported operation_type: {operation_type}"
        obj.save(update_fields=["status", "error_message", "updated_at"])
        raise ValidationError({"operation_type": "Unsupported offline operation."})

    try:
        if operation_type == "order_payment":
            _finalize_order_payment(
                obj=obj,
                tenant_id=tenant_id,
                outlet=outlet,
                user=user,
                payload=payload,
            )
        elif operation_type == "order_create":
            _finalize_order_create(
                obj=obj,
                tenant_id=tenant_id,
                membership=membership,
                outlet=outlet,
                user=user,
                payload=payload,
            )
        else:
            _finalize_order_add_lines(
                obj=obj,
                tenant_id=tenant_id,
                membership=membership,
                outlet=outlet,
                user=user,
                payload=payload,
            )
    except Exception as exc:
        obj.status = OfflineQueueStatus.FAILED
        obj.error_message = str(exc)[:2000]
        obj.save(update_fields=["status", "error_message", "updated_at"])
        raise

    return obj, False
