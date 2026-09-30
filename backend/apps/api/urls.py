from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter
from .auth_views import TokenObtainPairThrottledView, TokenRefreshThrottledView

from apps.audit.views import AuditEventViewSet
from apps.inventory.views import (
    StockBalanceViewSet,
    StockCountSessionViewSet,
    StockMovementViewSet,
    StockTransferViewSet,
)
from apps.catalog.views import (
    MenuCategoryViewSet,
    MenuItemViewSet,
    ModifierGroupViewSet,
    ModifierOptionViewSet,
    PromotionViewSet,
)
from apps.events.views import EventBookingViewSet, EventSpaceViewSet
from apps.finance.views import CashbookEntryViewSet, FinanceCategoryViewSet
from apps.integrations.views import IntegrationLinkViewSet
from apps.lodging.views import (
    FolioViewSet,
    ReservationViewSet,
    RoomRateWindowViewSet,
    RoomTypeViewSet,
    RoomViewSet,
)
from apps.pos.kds_views import KdsTicketView
from apps.pos.catalog_sync_views import PosCatalogVersionView
from apps.pos.offline_views import OfflineQueueBatchSubmitView, OfflineQueueSubmitView
from apps.pos.views import OrderViewSet, TableViewSet
from apps.pos.register_views import RegisterShiftViewSet
from apps.purchasing.views import PurchaseOrderViewSet, SupplierViewSet

from . import views
from .invite_views import InviteAcceptView, InviteCreateView
from .password_views import PasswordResetConfirmView, PasswordResetRequestView
from .payment_webhook_views import PaymentProviderWebhookView
from .report_views import OperationsRollupView, SalesSummaryView
from .signup_views import PublicSignupView

router = DefaultRouter()
router.register(r"menu/categories", MenuCategoryViewSet, basename="menu-category")
router.register(r"menu/items", MenuItemViewSet, basename="menu-item")
router.register(r"menu/promotions", PromotionViewSet, basename="promotion")
router.register(r"menu/modifier-groups", ModifierGroupViewSet, basename="modifier-group")
router.register(r"menu/modifier-options", ModifierOptionViewSet, basename="modifier-option")
router.register(r"events/spaces", EventSpaceViewSet, basename="event-space")
router.register(r"events/bookings", EventBookingViewSet, basename="event-booking")
router.register(r"finance/categories", FinanceCategoryViewSet, basename="finance-category")
router.register(r"finance/entries", CashbookEntryViewSet, basename="finance-entry")
router.register(r"integrations/links", IntegrationLinkViewSet, basename="integration-link")
router.register(r"tables", TableViewSet, basename="table")
router.register(r"pos/shifts", RegisterShiftViewSet, basename="pos-shift")
router.register(r"orders", OrderViewSet, basename="order")
router.register(r"stock/balances", StockBalanceViewSet, basename="stock-balance")
router.register(r"stock/movements", StockMovementViewSet, basename="stock-movement")
router.register(r"stock/transfers", StockTransferViewSet, basename="stock-transfer")
router.register(r"stock/count-sessions", StockCountSessionViewSet, basename="stock-count-session")
router.register(r"purchasing/suppliers", SupplierViewSet, basename="purchasing-supplier")
router.register(r"purchasing/purchase-orders", PurchaseOrderViewSet, basename="purchase-order")
router.register(r"lodging/room-types", RoomTypeViewSet, basename="room-type")
router.register(r"lodging/rate-windows", RoomRateWindowViewSet, basename="room-rate-window")
router.register(r"lodging/rooms", RoomViewSet, basename="room")
router.register(r"lodging/reservations", ReservationViewSet, basename="reservation")
router.register(r"lodging/folios", FolioViewSet, basename="folio")
router.register(r"audit-events", AuditEventViewSet, basename="audit-event")

urlpatterns = [
    path("schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path(
        "schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="api-schema"),
        name="api-schema-swagger-ui",
    ),
    path(
        "schema/redoc/",
        SpectacularRedocView.as_view(url_name="api-schema"),
        name="api-schema-redoc",
    ),
    path("health/", views.health, name="api-health"),
    path("auth/token/", TokenObtainPairThrottledView.as_view(), name="token_obtain_pair"),
    path("auth/token/refresh/", TokenRefreshThrottledView.as_view(), name="token_refresh"),
    path("auth/signup/", PublicSignupView.as_view(), name="auth-signup"),
    path("auth/password/reset/", PasswordResetRequestView.as_view(), name="auth-password-reset"),
    path(
        "auth/password/reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="auth-password-reset-confirm",
    ),
    path("me/", views.MeView.as_view(), name="api-me"),
    path("tenant/settings/", views.TenantSettingsView.as_view(), name="tenant-settings"),
    path("reports/sales-summary/", SalesSummaryView.as_view(), name="report-sales-summary"),
    path("reports/operations-rollup/", OperationsRollupView.as_view(), name="report-operations-rollup"),
    path(
        "integrations/payment-webhook/",
        PaymentProviderWebhookView.as_view(),
        name="integrations-payment-webhook",
    ),
    path("kds/tickets/", KdsTicketView.as_view(), name="kds-tickets"),
    path("pos/offline-sync/batch/", OfflineQueueBatchSubmitView.as_view(), name="pos-offline-sync-batch"),
    path("pos/offline-sync/", OfflineQueueSubmitView.as_view(), name="pos-offline-sync"),
    path("pos/catalog-version/", PosCatalogVersionView.as_view(), name="pos-catalog-version"),
    path("invites/", InviteCreateView.as_view(), name="invite-create"),
    path("invites/accept/", InviteAcceptView.as_view(), name="invite-accept"),
    path("", include(router.urls)),
]
