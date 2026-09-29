from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access.outlets import membership_outlet_ids
from apps.pos.models import Payment, Refund

from .permissions import HasTenantContext
from .report_queries import parse_outlet_uuid_param, parse_report_dates_from_query


class SalesSummaryView(APIView):
    """
    Aggregated payment and refund totals for a date range (UTC calendar dates on ``created_at``).
    """

    permission_classes = [IsAuthenticated, HasTenantContext]

    @extend_schema(
        parameters=[
            OpenApiParameter("date_from", OpenApiTypes.DATE, required=True),
            OpenApiParameter("date_to", OpenApiTypes.DATE, required=True),
            OpenApiParameter("outlet", OpenApiTypes.UUID, required=False),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request) -> Response:
        rng = parse_report_dates_from_query(
            request.query_params.get("date_from"),
            request.query_params.get("date_to"),
        )
        if isinstance(rng, Response):
            return rng

        outlet_res = parse_outlet_uuid_param(request.query_params.get("outlet"))
        if isinstance(outlet_res, Response):
            return outlet_res
        oid = outlet_res

        tenant_id = request.tenant.id
        allowed_outlets = membership_outlet_ids(request.tenant_membership)
        payments_qs = Payment.objects.filter(
            tenant_id=tenant_id,
            order__outlet_id__in=allowed_outlets,
            created_at__gte=rng.start,
            created_at__lte=rng.end,
        ).select_related("order", "order__outlet")
        if oid is not None:
            payments_qs = payments_qs.filter(order__outlet_id=oid)

        pay_agg = payments_qs.aggregate(
            payment_count=Count("id"),
            gross_sales=Sum("amount"),
        )
        gross = pay_agg["gross_sales"] or Decimal("0.00")
        pay_count = pay_agg["payment_count"] or 0

        refunds_qs = Refund.objects.filter(
            tenant_id=tenant_id,
            order__outlet_id__in=allowed_outlets,
            created_at__gte=rng.start,
            created_at__lte=rng.end,
        ).select_related("order")
        if oid is not None:
            refunds_qs = refunds_qs.filter(order__outlet_id=oid)

        ref_agg = refunds_qs.aggregate(
            refund_count=Count("id"),
            refund_total=Sum("amount"),
        )
        ref_total = ref_agg["refund_total"] or Decimal("0.00")
        ref_count = ref_agg["refund_count"] or 0

        by_method_raw = list(
            payments_qs.values("method").annotate(count=Count("id"), amount=Sum("amount")).order_by("method")
        )
        by_method = [
            {
                "method": r["method"],
                "count": r["count"],
                "amount": str(r["amount"] or Decimal("0.00")),
            }
            for r in by_method_raw
        ]

        by_outlet_raw = list(
            payments_qs.values("order__outlet_id", "order__outlet__name")
            .annotate(count=Count("id"), amount=Sum("amount"))
            .order_by("order__outlet__name")
        )
        by_outlet = [
            {
                "outlet_id": str(r["order__outlet_id"]),
                "outlet_name": r["order__outlet__name"],
                "count": r["count"],
                "amount": str(r["amount"] or Decimal("0.00")),
            }
            for r in by_outlet_raw
        ]

        net = (gross - ref_total).quantize(Decimal("0.01"))

        return Response(
            {
                "date_from": str(rng.d0),
                "date_to": str(rng.d1),
                "payments": {
                    "count": pay_count,
                    "gross_sales": str(gross),
                },
                "refunds": {
                    "count": ref_count,
                    "total": str(ref_total),
                },
                "net_sales": str(net),
                "by_payment_method": by_method,
                "by_outlet": by_outlet,
            }
        )


class OperationsRollupView(APIView):
    """
    Daily rollups (payments, refunds, net) for dashboards and scheduled reports.
    Same date filters as sales summary; adds **by_day** time series.
    """

    permission_classes = [IsAuthenticated, HasTenantContext]

    @extend_schema(
        parameters=[
            OpenApiParameter("date_from", OpenApiTypes.DATE, required=True),
            OpenApiParameter("date_to", OpenApiTypes.DATE, required=True),
            OpenApiParameter("outlet", OpenApiTypes.UUID, required=False),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request) -> Response:
        rng = parse_report_dates_from_query(
            request.query_params.get("date_from"),
            request.query_params.get("date_to"),
        )
        if isinstance(rng, Response):
            return rng

        outlet_res = parse_outlet_uuid_param(request.query_params.get("outlet"))
        if isinstance(outlet_res, Response):
            return outlet_res
        oid = outlet_res

        tenant_id = request.tenant.id
        allowed_outlets = membership_outlet_ids(request.tenant_membership)

        payments_qs = Payment.objects.filter(
            tenant_id=tenant_id,
            order__outlet_id__in=allowed_outlets,
            created_at__gte=rng.start,
            created_at__lte=rng.end,
        ).select_related("order", "order__outlet")
        if oid is not None:
            payments_qs = payments_qs.filter(order__outlet_id=oid)

        refunds_qs = Refund.objects.filter(
            tenant_id=tenant_id,
            order__outlet_id__in=allowed_outlets,
            created_at__gte=rng.start,
            created_at__lte=rng.end,
        ).select_related("order")
        if oid is not None:
            refunds_qs = refunds_qs.filter(order__outlet_id=oid)

        pay_by_day = {
            str(r["day"]): (r["amount"] or Decimal("0"), r["count"])
            for r in payments_qs.annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(amount=Sum("amount"), count=Count("id"))
        }
        ref_by_day = {
            str(r["day"]): (r["amount"] or Decimal("0"), r["count"])
            for r in refunds_qs.annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(amount=Sum("amount"), count=Count("id"))
        }
        all_days = sorted(set(pay_by_day.keys()) | set(ref_by_day.keys()))
        by_day = []
        for day in all_days:
            pa, pc = pay_by_day.get(day, (Decimal("0"), 0))
            ra, rc = ref_by_day.get(day, (Decimal("0"), 0))
            day_net = (pa - ra).quantize(Decimal("0.01"))
            by_day.append(
                {
                    "date": day,
                    "payments": str(pa),
                    "payment_count": pc,
                    "refunds": str(ra),
                    "refund_count": rc,
                    "net_sales": str(day_net),
                }
            )

        gross = payments_qs.aggregate(s=Sum("amount"))["s"] or Decimal("0")
        ref_total = refunds_qs.aggregate(s=Sum("amount"))["s"] or Decimal("0")
        net = (gross - ref_total).quantize(Decimal("0.01"))

        return Response(
            {
                "date_from": str(rng.d0),
                "date_to": str(rng.d1),
                "net_sales": str(net),
                "by_day": by_day,
            }
        )
