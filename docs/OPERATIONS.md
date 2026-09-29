# Operations runbook

## Daily opening checks

- Confirm the correct workspace, branch, and section are selected.
- Confirm staff can access only the areas required by their role.
- Review open orders, preparation queue, arrivals, departures, room readiness, events, low stock, and outstanding purchase orders.
- Open the correct POS shift before accepting payments.
- Confirm printers, barcode scanners, and network connectivity at each workstation.

## Daily closing checks

- Settle or explain open orders and folios.
- Reconcile cash, card, mobile money, and other payment methods against the shift totals.
- Review voids, refunds, supermarket returns, discounts, and unusual stock movements.
- Close shifts using the recorded counted amount.
- Review the daily operations digest and audit activity.
- Confirm the scheduled database backup completed.

## Restaurant and bar

- Use tables and tabs for seated or running orders.
- Route preparation items through the preparation queue.
- Keep modifiers and recipes current so pricing and stock consumption remain reliable.
- Record voids and refunds through their workflows; do not edit historical payment records directly.

## Supermarket and retail

- Configure barcode and weighted-item behavior before sale.
- Receive stock through purchase receipts or explicit stock receiving movements.
- Use transfers for section-to-section movement and stock takes for counted reconciliation.
- Process customer returns against the original order line when available.

## Hotel and lodging

- Review arrivals, in-house guests, departures, housekeeping, and maintenance before assigning rooms.
- Check in and check out through the reservation workflow.
- Post room and incidental charges to the guest folio.
- Record every folio payment with its method and reference.
- Do not close a folio with an unexplained balance.

## Events and services

- Check space availability and the weekly calendar before confirming bookings.
- Keep service packages and prices current.
- Record deposits and final settlement through the supported finance or order workflow.

## Purchasing and inventory

- Raise a purchase order before receipt where operationally possible.
- Record each supplier delivery as a receipt; partial deliveries remain open and visible.
- Investigate negative stock, large adjustments, repeated wastage, and stale purchase orders.
- Do not delete receipt or movement history to correct an error; post an auditable correcting movement.

## Incident triage

### Staff cannot see a module

1. Confirm the active workspace and section.
2. Confirm the workspace module is enabled.
3. Confirm the section policy enables it.
4. Confirm the membership role grants access.
5. Review the audit history for recent changes.

### Totals do not reconcile

1. Identify the workspace, section, business date, shift, order, or folio.
2. Compare charges, payments, refunds, and returns.
3. Check idempotency references and automatic finance posting links.
4. Check whether the issue is display-only or persisted data.
5. Preserve evidence before applying a correcting transaction.

### Stock is wrong

1. Inspect the stock ledger rather than only the current balance.
2. Review receipts, sales consumption, transfers, returns, counts, and adjustments.
3. Confirm the item and outlet are correct.
4. Post a documented correcting movement after approval.

### Background queue is delayed

1. Check Redis connectivity.
2. Check Celery worker and scheduler health.
3. Review failed task logs and retry policy.
4. Confirm provider failures are not being reported as local success.

## Backup and recovery

- Use automated encrypted PostgreSQL backups with retention appropriate to the business.
- Test restoration on an isolated database regularly.
- Record recovery point and recovery time results.
- A backup job marked successful is not proof that the backup restores correctly.
