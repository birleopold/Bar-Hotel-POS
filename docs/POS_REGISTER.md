# Retail register shift

At the retail or supermarket section, open **Shift close & cash** before taking sales. Count the opening cash float and record it when starting the shift. Named workstations can each have one open shift in the same section. A section-wide shift or an older time-window shift prevents additional tills from opening until it closes. Open, close and settlement serialize through the section lock; database constraints also prevent duplicate open shifts on a workstation.

The open-shift screen displays opening cash, recorded cash sales, recorded cash refunds, and the expected cash in the drawer. For new shifts, amounts come from payments received by that shift and refunds paid out by that shift. A refund can be paid from a different register than the original sale. Older shifts retain their original time-window calculation. Card payments and refunds against card payments do not affect this cash figure.

At close, count the physical cash independently and enter that amount. The saved shift records the expected amount, counted amount, and close time. Recent shifts show the difference (`counted − expected`), including shortages as negative values. If the drawer has cash drops, payouts, or other unrecorded movements, explain and reconcile those separately; the register calculation does not invent entries for them. The preview can change if a sale or refund is recorded before the close transaction completes, so the saved close figures are authoritative.

The local SQLite suite checks that the preview and close use the same calculation. A PostgreSQL-only test in `backend/tests/test_postgres_settlement_concurrency.py` checks simultaneous shift opens using separate connections and must be run against a disposable PostgreSQL database. Real cash handling and printer checks still need an on-site pass.

## Named workstations

Open **Workstations** from the register screen or office sidebar. An owner or tenant administrator can add a device name, unique workspace device code, section and printer/drawer/KDS labels. Staff see only devices in their accessible sections and can select an enabled device for this browser. The signed selection remains across worker lock/handoff, but never grants membership, PIN access or section permissions. Disabled devices and devices outside the current membership are ignored. Clear selection removes it from this browser.

Opening a shift in the selected device's section records the workstation and opening worker. Existing shifts retain their original section identity. Close a device's open shift before disabling it or moving it to a different section. All edits and selections are audited. **One open shift per named workstation is the rule.** Select each device before opening/reconciling its drawer. The register page shows other open tills, but a close action must match this browser's selected register. Formal cashier handover, cash drops/payouts and strong device pairing remain tracked in the full suite checklist.

Printer, drawer and KDS fields are configuration labels, not printer drivers or active routing. Last contact is updated on workstation/register screen use and is not an online/health guarantee. PostgreSQL RLS migration follows the existing optional tenant isolation pattern. Physical printers, PostgreSQL concurrency and visual browser certification require separate evidence.

## Payment, refund and offline attribution

The staff order and refund screens show the selected till. With no device selected, a payment/refund can automatically use the only open shift. If several are open, select a till first; ambiguous attribution is rejected before money is posted. A configured, selected till must have an open shift. Existing integrations with no open shifts can still record unassigned payments; those do not appear in a new register's totals. Do not treat unassigned payments as reconciled drawer cash.

API payment, refund and linked-return requests accept optional `workstation_id` and `shift_id`. Read payment/refund responses expose `shift_id`. Use `GET /api/v1/pos/shifts/?outlet=OUTLET_UUID&workstation=DEVICE_UUID&status=open` to capture the original shift for a client. This endpoint is read-only and tenant/outlet-scoped. It reports stored close amounts; an open shift's stored expected amount is its starting float, not a live cash preview.

Offline `order_payment` payloads from configured workstation sections must include their original `shift_id`. A new delayed tender targeting a closed shift is rejected for operator review rather than being assigned to the next cashier. The existing rejection path does not provide a complete persisted conflict-resolution workflow; that is still in the offline checklist. An already-applied action can replay after close, retaining its original link. Reusing an idempotency key with another specified workstation or shift is rejected.

Migration 0013 preserves all existing shift amounts and marks existing shifts for legacy time-window accounting. Existing payments/refunds keep nullable, unassigned links; there is no speculative historical attribution. Close legacy shifts before opening concurrent named tills. New shifts use explicit links. Back up the database before upgrading. Schema reverse/reapply was checked only on disposable data; after recording new attributed transactions, rollback should restore a matching backup and code version, because reversing this migration removes the attribution fields.


## Approved browsers

Owners and tenant administrators can open **Workstations → Browser approvals**, confirm their account password and name the browser being approved. Administration requires a password-authenticated session. New workstations created through staff configuration require approval by default; existing workstations remain opt-in. Approval expires after 30 days and remains attached to the browser through worker PIN changes.

Remote revocation records a reason and locks the affected PIN session on its next request. Detaching the current browser revokes its current approval and clears selection. Expired, revoked or modified credentials cannot operate required-pairing staff registers or unlock their PIN terminal. Moving/disabling a station revokes approvals; close an open shift before moving, disabling or changing its approval policy. Browser approval does not grant worker permissions or prove physical hardware identity. API clients retain authenticated account authorization and explicit shift attribution.

Phase 01 source implementation is complete. Cash drops/payouts and formal handover remain checklist item 04; device adapters and printer tests remain item 15. PostgreSQL, browser and hardware evidence is tracked separately.
