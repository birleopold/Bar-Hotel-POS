from datetime import date
from decimal import Decimal

import pytest
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Membership, MembershipRole, User
from apps.catalog.models import MenuCategory, MenuItem
from apps.finance.models import CashbookEntry, FinanceCategoryKind
from apps.integrations.efris import UraEfrisHttpAdapter
from apps.integrations.models import IntegrationLink
from apps.inventory.models import StockBalance
from apps.inventory.services import validate_and_consume_stock_for_paid_order
from apps.lodging.models import Reservation, Room, RoomRateWindow, RoomType
from apps.lodging.serializers import ReservationSerializer, RoomSerializer
from apps.lodging.services import check_in_reservation
from apps.pos.models import Order, OrderLine
from apps.pos.services import record_order_payment, record_order_refund
from apps.staff.services import get_tenant_staff_modules, staff_nav_visibility_scoped
from apps.tenants.models import Outlet, Site, Tenant, TenantSettings


@pytest.mark.django_db
class TestCriticalWorkflowGuards:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="Guard Tenant", slug="guard-tenant")
        TenantSettings.objects.create(tenant=self.tenant, default_currency="UGX")
        self.site = Site.objects.create(tenant=self.tenant, name="Main")
        self.outlet = Outlet.objects.create(site=self.site, name="Bar", outlet_type="bar")
        self.user = User.objects.create_user(email="guard@example.invalid", password="AuditOnly!926")
        self.member = Membership.objects.create(user=self.user, tenant=self.tenant, role=MembershipRole.SERVER)
        self.client = APIClient()
        self.headers = {"HTTP_X_TENANT_ID": str(self.tenant.id)}

    def test_jwt_resolves_tenant_context(self):
        token = str(RefreshToken.for_user(self.user).access_token)
        response = self.client.get(
            "/api/v1/finance/categories/",
            HTTP_AUTHORIZATION="Bearer " + token,
            **self.headers,
        )
        assert response.status_code == 200

    def test_server_cannot_read_integration_secrets_or_issue_refund(self):
        IntegrationLink.objects.create(
            tenant=self.tenant,
            provider_key="efris",
            settings={"client_secret": "dummy-secret"},
        )
        self.client.force_login(self.user)
        assert self.client.get("/api/v1/integrations/links/", **self.headers).status_code == 403

        order = Order.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            created_by=self.user,
            subtotal=Decimal("100"),
            total=Decimal("100"),
            currency="UGX",
        )
        record_order_payment(
            order=order,
            user=self.user,
            amount=Decimal("100"),
            method="cash",
            idempotency_key="guard-payment",
        )
        response = self.client.post(
            f"/api/v1/orders/{order.pk}/refunds/",
            {"amount": "100.00", "reason": "Guard"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="guard-refund",
            **self.headers,
        )
        assert response.status_code == 403

    def test_refund_posts_accounting_reversal(self):
        order = Order.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            created_by=self.user,
            subtotal=Decimal("100"),
            total=Decimal("100"),
            currency="UGX",
        )
        record_order_payment(
            order=order,
            user=self.user,
            amount=Decimal("100"),
            method="cash",
            idempotency_key="payment-reversal",
        )
        record_order_refund(
            order=order,
            user=self.user,
            amount=Decimal("100"),
            reason="Reversal",
            idempotency_key="refund-reversal",
            restock=False,
        )
        assert set(CashbookEntry.objects.values_list("category__kind", "amount")) == {
            (FinanceCategoryKind.INCOME, Decimal("100")),
            (FinanceCategoryKind.EXPENSE, Decimal("100")),
        }

    def test_reservation_status_patch_cannot_bypass_checkin(self):
        room_type = RoomType.objects.create(tenant=self.tenant, site=self.site, name="Standard")
        room = Room.objects.create(room_type=room_type, name="101")
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            site=self.site,
            room=room,
            guest_name="Guest",
            check_in=date(2026, 9, 21),
            check_out=date(2026, 9, 22),
        )
        self.client.force_login(self.user)
        response = self.client.patch(
            f"/api/v1/lodging/reservations/{reservation.pk}/",
            {"status": "checked_in"},
            format="json",
            **self.headers,
        )
        assert response.status_code == 200
        reservation.refresh_from_db()
        assert reservation.status == "confirmed"

    def test_checkin_rejects_unavailable_room_and_uses_tenant_currency(self):
        room_type = RoomType.objects.create(tenant=self.tenant, site=self.site, name="Standard")
        room = Room.objects.create(room_type=room_type, name="101", status="out_of_order")
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            site=self.site,
            room=room,
            guest_name="Guest",
            check_in=date(2026, 9, 21),
            check_out=date(2026, 9, 22),
        )
        with pytest.raises(ValidationError):
            check_in_reservation(reservation=reservation, user=self.user)
        room.status = "clean"
        room.save(update_fields=["status"])
        RoomRateWindow.objects.create(
            room_type=room_type,
            valid_from=date(2026, 9, 1),
            nightly_amount=Decimal("120000"),
        )
        checked_in = check_in_reservation(reservation=reservation, user=self.user)
        assert checked_in.folios.get().currency == "UGX"

    def test_duplicate_lines_are_aggregated_before_stock_deduction(self):
        category = MenuCategory.objects.create(tenant=self.tenant, name="Drinks")
        item = MenuItem.objects.create(
            tenant=self.tenant,
            category=category,
            name="Water",
            unit_price=Decimal("1"),
            track_inventory=True,
        )
        StockBalance.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            menu_item=item,
            quantity=Decimal("5"),
        )
        order = Order.objects.create(tenant=self.tenant, outlet=self.outlet, currency="UGX")
        for _ in range(2):
            OrderLine.objects.create(
                order=order,
                menu_item=item,
                label="Water",
                quantity=Decimal("3"),
                unit_price=Decimal("1"),
                line_total=Decimal("3"),
            )
        with pytest.raises(ValidationError):
            validate_and_consume_stock_for_paid_order(order, self.user)
        assert StockBalance.objects.get(outlet=self.outlet, menu_item=item).quantity == Decimal("5")

    def test_room_scope_and_unconfirmed_efris_response_are_rejected(self):
        blocked = Site.objects.create(tenant=self.tenant, name="Blocked")
        self.member.sites.add(self.site)
        room_type = RoomType.objects.create(tenant=self.tenant, site=blocked, name="Blocked")
        request = APIRequestFactory().post("/")
        request.tenant = self.tenant
        request.tenant_membership = self.member
        serializer = RoomSerializer(
            data={"room_type": str(room_type.pk), "name": "999"},
            context={"request": request},
        )
        assert not serializer.is_valid()
        assert "room_type" in serializer.errors
        result = UraEfrisHttpAdapter()._normalize_submit_response(status_code=200, body={})
        assert not result.success

    def test_property_lodging_remains_visible_while_bar_is_selected(self):
        settings = self.tenant.settings
        settings.business_lines = ["lodging", "bar"]
        settings.save(update_fields=["business_lines", "updated_at"])
        self.member.role = MembershipRole.OWNER
        self.member.save(update_fields=["role", "updated_at"])
        modules = get_tenant_staff_modules(self.tenant, outlet=self.outlet)
        visibility = staff_nav_visibility_scoped(
            self.member,
            modules=modules,
            tenant=self.tenant,
            outlet=self.outlet,
        )
        assert visibility.lodging
