from __future__ import annotations

import uuid
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils.dateparse import parse_date
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.datetime_bounds import utc_day_range_inclusive
from apps.pos.models import Payment, Refund

from .permissions import HasTenantContext


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
        df_raw = request.query_params.get("date_from")
        dt_raw = request.query_params.get("date_to")
        if not df_raw or not dt_raw:
            return Response(
                {
                    "error": {
                        "code": "dates_required",
                        "message": "Query parameters date_from and date_to are required (YYYY-MM-DD).",
                    }
                },
                status=400,
            )
        d0 = parse_date(str(df_raw))
        d1 = parse_date(str(dt_raw))
        if d0 is None or d1 is None:
            return Response(
                {
                    "error": {
                        "code": "invalid_date",
                        "message": "date_from and date_to must be valid dates.",
                    }
                },
                status=400,
            )
        if d0 > d1:
            return Response(
                {
                    "error": {
                        "code": "invalid_range",
                        "message": "date_from must be on or before date_to.",
                    }
                },
                status=400,
            )

        start, end = utc_day_range_inclusive(d0, d1)

        tenant_id = request.tenant.id
        payments_qs = Payment.objects.filter(
            tenant_id=tenant_id,
            created_at__gte=start,
            created_at__lte=end,
        ).select_related("order", "order__outlet")

        outlet_param = request.query_params.get("outlet")
        if outlet_param:
            try:
                oid = uuid.UUID(str(outlet_param))
            except ValueError:
                return Response(
                    {"error": {"code": "invalid_outlet", "message": "outlet must be a UUID."}},
                    status=400,
                )
            payments_qs = payments_qs.filter(order__outlet_id=oid)

        pay_agg = payments_qs.aggregate(
            payment_count=Count("id"),
            gross_sales=Sum("amount"),
        )
        gross = pay_agg["gross_sales"] or Decimal("0.00")
        pay_count = pay_agg["payment_count"] or 0

        refunds_qs = Refund.objects.filter(
            tenant_id=tenant_id,
            created_at__gte=start,
            created_at__lte=end,
        ).select_related("order")
        if outlet_param:
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
                "date_from": str(d0),
                "date_to": str(d1),
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
        df_raw = request.query_params.get("date_from")
        dt_raw = request.query_params.get("date_to")
        if not df_raw or not dt_raw:
            return Response(
                {
                    "error": {
                        "code": "dates_required",
                        "message": "Query parameters date_from and date_to are required (YYYY-MM-DD).",
                    }
                },
                status=400,
            )
        d0 = parse_date(str(df_raw))
        d1 = parse_date(str(dt_raw))
        if d0 is None or d1 is None:
            return Response(
                {
                    "error": {
                        "code": "invalid_date",
                        "message": "date_from and date_to must be valid dates.",
                    }
                },
                status=400,
            )
        if d0 > d1:
            return Response(
                {
                    "error": {
                        "code": "invalid_range",
                        "message": "date_from must be on or before date_to.",
                    }
                },
                status=400,
            )
        start, end = utc_day_range_inclusive(d0, d1)
        tenant_id = request.tenant.id

        payments_qs = Payment.objects.filter(
            tenant_id=tenant_id,
            created_at__gte=start,
            created_at__lte=end,
        ).select_related("order", "order__outlet")

        outlet_param = request.query_params.get("outlet")
        if outlet_param:
            try:
                oid = uuid.UUID(str(outlet_param))
            except ValueError:
                return Response(
                    {"error": {"code": "invalid_outlet", "message": "outlet must be a UUID."}},
                    status=400,
                )
            payments_qs = payments_qs.filter(order__outlet_id=oid)

        refunds_qs = Refund.objects.filter(
            tenant_id=tenant_id,
            created_at__gte=start,
            created_at__lte=end,
        )
        if outlet_param:
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
            net = (pa - ra).quantize(Decimal("0.01"))
            by_day.append(
                {
                    "date": day,
                    "payments": str(pa),
                    "payment_count": pc,
                    "refunds": str(ra),
                    "refund_count": rc,
                    "net_sales": str(net),
                }
            )

        gross = payments_qs.aggregate(s=Sum("amount"))["s"] or Decimal("0")
        ref_total = refunds_qs.aggregate(s=Sum("amount"))["s"] or Decimal("0")
        net = (gross - ref_total).quantize(Decimal("0.01"))

        return Response(
            {
                "date_from": str(d0),
                "date_to": str(d1),
                "net_sales": str(net),
                "by_day": by_day,
            }
        )
