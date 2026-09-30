# Retail register shift

At the retail or supermarket section, open **Shift close & cash** before taking sales. Count the opening cash float and record it when starting the shift. Only one shift should be open for a section at a time; the service locks the section when opening to prevent concurrent opens.

The open-shift screen displays opening cash, recorded cash sales, recorded cash refunds, and the expected cash in the drawer. The amounts come from payments and refunds recorded since the shift opened. Card payments and refunds against card payments do not affect this cash figure.

At close, count the physical cash independently and enter that amount. The saved shift records the expected amount, counted amount, and close time. Recent shifts show the difference (`counted − expected`), including shortages as negative values. If the drawer has cash drops, payouts, or other unrecorded movements, explain and reconcile those separately; the register calculation does not invent entries for them. The preview can change if a sale or refund is recorded before the close transaction completes, so the saved close figures are authoritative.

The local SQLite suite checks that the preview and close use the same calculation. A PostgreSQL-only test in `backend/tests/test_postgres_settlement_concurrency.py` checks simultaneous shift opens using separate connections and must be run against a disposable PostgreSQL database. Real cash handling and printer checks still need an on-site pass.

## Named workstations

Open **Workstations** from the register screen or office sidebar. An owner or tenant administrator can add a device name, unique workspace device code, section and printer/drawer/KDS labels. Staff see only devices in their accessible sections and can select an enabled device for this browser. The signed selection remains across worker lock/handoff, but never grants membership, PIN access or section permissions. Disabled devices and devices outside the current membership are ignored. Clear selection removes it from this browser.

Opening a shift in the selected device's section records the workstation and opening worker. Existing shifts retain their original section identity. Close a device's open shift before disabling it or moving it to a different section. All edits and selections are audited. **One open shift per section remains the rule:** sales/refunds are still reconciled at section level; this checkpoint does not authorize multiple simultaneous cash drawers. Workstation-specific payment attribution and formal cashier handover are tracked in the full suite checklist.

Printer, drawer and KDS fields are configuration labels, not printer drivers or active routing. Last contact is updated on workstation/register screen use and is not an online/health guarantee. PostgreSQL RLS migration follows the existing optional tenant isolation pattern. Physical printers, PostgreSQL concurrency and visual browser certification require separate evidence.
