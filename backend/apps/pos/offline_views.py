from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.api.permissions import HasTenantContext, HasTenantModule, NotReadOnlyRole
from apps.tenants.models import Outlet

from .serializers import (
    OfflineQueueBatchSerializer,
    OfflineQueueCreateSerializer,
    OfflineQueuedOperationSerializer,
)
from .services.catalog_version import catalog_version_payload
from .services.offline import process_offline_queue_entry, record_catalog_stale_rejection


def catalog_stale_response_if_needed(*, tenant_id, outlet: Outlet, payload: dict) -> Response | None:
    if not payload:
        return None
    client_cv = (payload.get("catalog_version") or "").strip()
    if not client_cv:
        return None
    server = catalog_version_payload(tenant_id=tenant_id, outlet_id=outlet.id)
    if client_cv == server["catalog_version"]:
        return None
    return Response(
        {
            "error": {
                "code": "catalog_stale",
                "message": (
                    "Menu or prices changed since the offline snapshot. "
                    "Refresh catalog (GET pos/catalog-version/) and retry."
                ),
                "server_catalog_version": server["catalog_version"],
                "as_of": server["as_of"],
            }
        },
        status=status.HTTP_409_CONFLICT,
    )


def _resolve_offline_outlet(request: Request, vd: dict) -> Outlet | None:
    return (
        Outlet.objects.filter(
            id=vd["outlet"],
            site__tenant_id=request.tenant.id,
            is_active=True,
        ).first()
    )


class OfflineQueueSubmitView(APIView):
    permission_classes = [IsAuthenticated, HasTenantContext, HasTenantModule, NotReadOnlyRole]
    required_staff_module = "pos"
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "offline_sync"

    @extend_schema(
        request=OfflineQueueCreateSerializer,
        responses={200: OpenApiTypes.OBJECT, 201: OpenApiTypes.OBJECT},
    )
    def post(self, request: Request) -> Response:
        ser = OfflineQueueCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        outlet = _resolve_offline_outlet(request, vd)
        if outlet is None:
            return Response(
                {"error": {"code": "invalid_outlet", "message": "Invalid outlet."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if vd["operation_type"] in ("order_create", "order_add_lines"):
            stale = catalog_stale_response_if_needed(
                tenant_id=request.tenant.id,
                outlet=outlet,
                payload=vd["payload"],
            )
            if stale is not None:
                record_catalog_stale_rejection(
                    tenant_id=request.tenant.id,
                    outlet=outlet,
                    client_mutation_id=vd["client_mutation_id"],
                    operation_type=vd["operation_type"],
                    payload=vd["payload"],
                    error_payload=stale.data,
                )
                return stale
        obj, replay = process_offline_queue_entry(
            tenant_id=request.tenant.id,
            membership=request.tenant_membership,
            outlet=outlet,
            user=request.user,
            client_mutation_id=vd["client_mutation_id"],
            operation_type=vd["operation_type"],
            payload=vd["payload"],
        )
        return Response(
            {
                "replay": replay,
                "queue": OfflineQueuedOperationSerializer(obj).data,
            },
            status=status.HTTP_200_OK if replay else status.HTTP_201_CREATED,
        )


class OfflineQueueBatchSubmitView(APIView):
    """
    Process up to 50 offline mutations in order.

    Each entry matches ``POST pos/offline-sync/`` plus optional **``depends_on``** (0-based
    index). For **``order_add_lines``** or **``order_payment``**: omit **``payload.order_id``**
    and set **``depends_on``** to an earlier operation whose result includes
    **``applied_order_id``** (e.g. **``order_create``** or **``order_add_lines``**). Do not send
    both **``order_id``** and **``depends_on``**.

    Per-item ``catalog_stale`` only fails that index. Response is always HTTP **200** with
    **``results[]``**; inspect each **``status_code``**.
    """

    permission_classes = [IsAuthenticated, HasTenantContext, HasTenantModule, NotReadOnlyRole]
    required_staff_module = "pos"
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "offline_batch"

    @extend_schema(
        request=OfflineQueueBatchSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request: Request) -> Response:
        ser = OfflineQueueBatchSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        operations = ser.validated_data["operations"]
        results: list[dict] = []

        for idx, vd in enumerate(operations):
            mid = vd["client_mutation_id"]
            vd_op = dict(vd)
            payload = dict(vd_op["payload"])
            dep = vd_op.get("depends_on")

            if dep is not None:
                if dep >= idx:
                    results.append(
                        {
                            "index": idx,
                            "client_mutation_id": mid,
                            "ok": False,
                            "status_code": status.HTTP_400_BAD_REQUEST,
                            "error": {
                                "code": "invalid_depends_on",
                                "message": "depends_on must be an earlier index (0 .. index-1).",
                            },
                        }
                    )
                    continue
                ref = results[dep]
                if not ref.get("ok"):
                    results.append(
                        {
                            "index": idx,
                            "client_mutation_id": mid,
                            "ok": False,
                            "status_code": status.HTTP_400_BAD_REQUEST,
                            "error": {
                                "code": "depends_on_failed",
                                "message": f"Operation at index {dep} did not succeed.",
                            },
                        }
                    )
                    continue
                parent_oid = (ref.get("queue") or {}).get("applied_order_id")
                if not parent_oid:
                    results.append(
                        {
                            "index": idx,
                            "client_mutation_id": mid,
                            "ok": False,
                            "status_code": status.HTTP_400_BAD_REQUEST,
                            "error": {
                                "code": "depends_on_no_order",
                                "message": "Prior operation did not expose applied_order_id.",
                            },
                        }
                    )
                    continue
                payload["order_id"] = parent_oid
                vd_op["payload"] = payload

            outlet = _resolve_offline_outlet(request, vd_op)
            if outlet is None:
                results.append(
                    {
                        "index": idx,
                        "client_mutation_id": mid,
                        "ok": False,
                        "status_code": status.HTTP_400_BAD_REQUEST,
                        "error": {"code": "invalid_outlet", "message": "Invalid outlet."},
                    }
                )
                continue

            if vd_op["operation_type"] in ("order_create", "order_add_lines"):
                stale = catalog_stale_response_if_needed(
                    tenant_id=request.tenant.id,
                    outlet=outlet,
                    payload=vd_op["payload"],
                )
                if stale is not None:
                    record_catalog_stale_rejection(
                        tenant_id=request.tenant.id,
                        outlet=outlet,
                        client_mutation_id=mid,
                        operation_type=vd_op["operation_type"],
                        payload=vd_op["payload"],
                        error_payload=stale.data,
                    )
                    results.append(
                        {
                            "index": idx,
                            "client_mutation_id": mid,
                            "ok": False,
                            "status_code": stale.status_code,
                            "error": stale.data.get("error", stale.data),
                        }
                    )
                    continue

            try:
                obj, replay = process_offline_queue_entry(
                    tenant_id=request.tenant.id,
                    membership=request.tenant_membership,
                    outlet=outlet,
                    user=request.user,
                    client_mutation_id=vd_op["client_mutation_id"],
                    operation_type=vd_op["operation_type"],
                    payload=vd_op["payload"],
                )
            except ValidationError as exc:
                results.append(
                    {
                        "index": idx,
                        "client_mutation_id": mid,
                        "ok": False,
                        "status_code": status.HTTP_400_BAD_REQUEST,
                        "error": exc.detail,
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "index": idx,
                        "client_mutation_id": mid,
                        "ok": False,
                        "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                        "error": {"code": "server_error", "message": str(exc)[:500]},
                    }
                )
            else:
                results.append(
                    {
                        "index": idx,
                        "client_mutation_id": mid,
                        "ok": True,
                        "status_code": (
                            status.HTTP_200_OK if replay else status.HTTP_201_CREATED
                        ),
                        "replay": replay,
                        "queue": OfflineQueuedOperationSerializer(obj).data,
                    }
                )

        return Response({"results": results}, status=status.HTTP_200_OK)
