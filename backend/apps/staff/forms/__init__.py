"""Staff Django forms (split by domain; import from ``apps.staff.forms`` as before)."""

from .auth import StaffLoginForm
from .events import StaffEventBookingForm, StaffEventSpaceForm
from .finance import StaffCashbookEntryForm, StaffFinanceCategoryForm
from .inventory import (
    StaffQuickTrackedMenuItemForm,
    StaffStockCountSessionForm,
    StaffStockMovementForm,
    StaffStockMovementUploadForm,
    StaffStockTransferForm,
)
from .lodging import StaffFolioManualLineForm, StaffReservationForm
from .pos_orders import (
    StaffOrderAdjustLineQuantityForm,
    StaffOrderAddLineForm,
    StaffOrderAddServiceForm,
    StaffOrderApplyPromotionForm,
    StaffOrderHoldForm,
    StaffOrderLineDiscountForm,
    StaffOrderReadyHandoffForm,
    StaffOrderLineReturnForm,
    StaffOrderPaymentForm,
    StaffOrderSetFolioForm,
    StaffOrderRefundForm,
    StaffOrderScanAddForm,
    StaffPosShiftCloseForm,
    StaffPosShiftOpenForm,
    StaffOrderVoidOrderForm,
    StaffOrderVoidLineForm,
    StaffTableForm,
)
from .promotions import StaffPromotionForm
from .purchasing import StaffPOHeaderForm, StaffSupplierForm
from .workspace_forms import (
    StaffEfrisSettingsForm,
    StaffIntegrationLinkForm,
    StaffMembershipBulkActionForm,
    StaffMembershipManageForm,
    StaffTeamInviteForm,
    StaffTenantBrandingForm,
    StaffTenantModulesForm,
    StaffWorkerCreateForm,
)

__all__ = [
    "StaffCashbookEntryForm",
    "StaffEfrisSettingsForm",
    "StaffEventBookingForm",
    "StaffEventSpaceForm",
    "StaffFinanceCategoryForm",
    "StaffFolioManualLineForm",
    "StaffIntegrationLinkForm",
    "StaffMembershipBulkActionForm",
    "StaffMembershipManageForm",
    "StaffLoginForm",
    "StaffOrderAdjustLineQuantityForm",
    "StaffOrderAddLineForm",
    "StaffOrderAddServiceForm",
    "StaffOrderApplyPromotionForm",
    "StaffOrderHoldForm",
    "StaffOrderLineDiscountForm",
    "StaffOrderReadyHandoffForm",
    "StaffOrderLineReturnForm",
    "StaffOrderPaymentForm",
    "StaffOrderSetFolioForm",
    "StaffPosShiftCloseForm",
    "StaffPosShiftOpenForm",
    "StaffOrderRefundForm",
    "StaffOrderScanAddForm",
    "StaffOrderVoidOrderForm",
    "StaffOrderVoidLineForm",
    "StaffPOHeaderForm",
    "StaffPromotionForm",
    "StaffQuickTrackedMenuItemForm",
    "StaffReservationForm",
    "StaffStockCountSessionForm",
    "StaffStockMovementForm",
    "StaffStockMovementUploadForm",
    "StaffStockTransferForm",
    "StaffSupplierForm",
    "StaffTableForm",
    "StaffTeamInviteForm",
    "StaffTenantBrandingForm",
    "StaffTenantModulesForm",
    "StaffWorkerCreateForm",
]
