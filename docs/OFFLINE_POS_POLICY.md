# Offline POS policy and staff conflict review

**Implementation status:** partial. The existing Django POS offline queue and batch API can apply permitted server-validated operations once the device reconnects. This is **not** a guarantee that a fully disconnected browser stores transactions safely; that requires a separately tested device-side persistent queue. The server page cannot see requests still only on an unplugged or disconnected terminal.

## What staff can safely do

| Situation | Current policy |
| --- | --- |
| New order when the terminal has queued it | Server validates item/menu snapshot and replays by original unique request ID on connection |
| Adding items to an existing order | Server rechecks catalog, permissions, status and inventory policies before applying |
| Cash collected in-person | Can be recorded through offline replay if the server validates order, shift and workstation attribution |
| Card, mobile money, bank or other electronic tender | **Do not represent as paid offline.** Verify with the provider once online and use the normal online payment workflow |
| Changed menu / price snapshot | Server rejects with `409 catalog_stale`; staff must refresh. Same mutation ID may only change its catalog fingerprint, not quantities or items |
| Retry after an already-applied request | Same request ID, same section, type and payload returns the prior result rather than posting twice |
| Reused ID with changed order, section or payment | Reject; do not silently rewrite an existing operation |
| Failure awaiting resolution | Keep the original request ID and original receipt/shift information. Manager records a review note; marking reviewed does not post cash or stock |
| Sync delayed | Server flags queue entries after configured exception policy hours (default 24) and shows them on the review screen |
| Workers sharing a terminal | Use individual PIN/password sessions and lock at handover; a server queue record is **not** a secure local browser transaction vault |

## Review procedure

1. Open **POS → Offline**. Check counts for applied, pending, failed and unreviewed operations.
2. Verify actual customer tender and shift against independent receipts and provider/bank information. A failed server replay is **not** proof the customer wasn't debited.
3. For `catalog_stale`, update the device's catalog and retry only the same operation with the new catalog fingerprint.
4. Do not invent a second payment or change its request ID to bypass idempotency. For an electronic tender, use the provider's online confirmation rather than a locally fabricated success.
5. A manager may record an evidence note for a failed operation. This records attribution without changing order, inventory, payment or fiscal posting.
6. Before shift reconciliation, review any outstanding per-device mutations which haven't reached the server. The staff page cannot see those until they synchronize.

## Server sync API

- `POST /api/v1/pos/offline-sync/` — one operation, original client mutation ID.
- `POST /api/v1/pos/offline-sync/batch/` — sequential operation batch with `depends_on` order references.
- `GET /api/v1/pos/catalog-version/` — current outlet catalog fingerprint.

All mutations must be attached to the correct tenant and a currently authorized outlet **before** recording a rejected catalog snapshot. Tenant/module and payment permissions are still checked when queued operations are applied.

## Operational limitations and planned follow-up

- No generic browser can securely promise EMV card acceptance while offline. Offline-card acceptance is device/provider/country specific; only add a certified integration under its provider's written rules. The web POS must not imply that capturing a card number is authorization.
- Existing server queue timestamps show *server receipt time*, not how long a device was disconnected before it transmitted. A client-side time and bounded local transaction limit will require authenticated device identity and tamper-resistance design.
- A cashier on a different shared browser cannot access operations stuck in another browser's local storage. Prove persistence, logout privacy and handover on real hardware before advertising offline-first.
- The queue monitors server-known failures only; no automatic retry from the manager page. Failed steps require investigation against the original operation and provider confirmations.
- Observed shift/workstation attribution must be preserved. No shift backdating, no fake electronic tender settlement or duplicate fiscal entry.
- Pending server operations are **not** guaranteed processed without a live connected device and correct request replay.

## Reference design

Square's publicly documented offline-card procedure is deliberately tied to specific readers and upload windows, and explicitly warns that merchants can be responsible for later declined or expired payments. It cannot be copied into an arbitrary web-based POS without equivalent certified processing and country/provider approval:

- https://squareup.com/help/us/en/article/7777-process-card-payments-with-offline-mode
- https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum

This project therefore takes the conservative route: allow offline cash recording, but do not invent settlement of card, bank or mobile money transactions.
