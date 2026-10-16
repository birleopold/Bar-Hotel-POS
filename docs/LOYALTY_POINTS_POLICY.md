# Customer rewards — current behaviour

Customer points are optional and **disabled for every tenant by default**.

## Owner setup

1. Sign in as tenant owner or administrator.
2. Open **Customers & Guests → Reward rules**, or **Workspace → Branding & defaults → Customer points**.
3. Select **Award customer points** and choose the amount of **default-currency spending needed to earn one point**. For example, UGX 10,000 per whole point.
4. Save workspace settings. Only future linked, fully paid POS orders earn points. Historical sales never receive automatic backdated rewards.
5. Open any permitted customer's profile to see current points, recorded awards and reversals. The owner may make an explicitly explained manual correction using an idempotent request ID.

## Eligibility and maths

- An order **must be linked to an active customer at the moment the last payment settles**. Split or partial tenders do not earn points until the order is fully paid.
- Order currency must match the workspace's **default currency**; there is no automatic exchange-rate assumption.
- Eligible amount is `min(order.total, max(0, order.subtotal - order.discount_amount))`. It excludes tax and order-level discounts. Existing item-level discounts are reflected in the posted subtotal.
- Points = **floor**(eligible amount / owner-configured spending per point), capped at **1,000,000 points per order** as a fraud/overflow guard.
- Each fully paid order gets at most **one** ledger award, keyed to the unique order ID. Payment retry with the same idempotency key does not award again.
- Example: default currency UGX, configured 10,000 UGX per point, net eligible sale UGX 85,000 → **8 points**, not 8.5 points.
- Turning off loyalty later stops **new** earnings but does not remove existing points or stop necessary reversal of returns from earlier eligible sales.

## Refunds and corrections

Refunds reverse points based on the **original earned award**, not today's earn rate.

After each refund:

```text
cumulative_target = floor(original_points * min(1, refunded_amount_to_date / original_order_total))
new_reversal = max(0, cumulative_target - points_already_reversed_for_that_order)
```

The reversal is part of the original POS refund database transaction. A duplicate refund message cannot post it again, and a full refund reverses the entire original award. The value of refunded goods may differ from the value used for point earning; the ratio uses the posted transaction total consistently.

If a customer already used or manually spent points, an ordinary POS refund must **not be blocked**. A reversal may temporarily make the point balance negative. The customer screen calls this **points to recover**; this is **not a demand for cash**, a debt collection mechanism or a negative wallet value. Managers may not use a manual negative correction to overdraw an account.

When verified duplicate customer records are merged, their original point entries are transferred with the underlying order links inside one database transaction; original sale and refund source keys do not change. Owners cannot simply re-link a closed rewarded order to another customer because that would split the transaction from its reward history.

## Features not yet enabled

- Checkout redemption/discount conversion, gift vouchers and free-item benefits.
- Tier status, birthday rewards, cross-tenant earning, transferable points, points expiration and customer self-service portal.
- Posting a financial liability/contract-performance obligation to the general ledger or EFRIS purely because points were awarded.
- Unreviewed exchange-rate conversions, automatic corrections to historic, previously paid orders, automatic customer identity merging.

**Accounting caution:** under IFRS 15, a reward that grants a customer a material right may require allocating transaction consideration to the future performance obligation. The treatment depends on the specific benefits, tax and contract terms; it cannot be inferred from the existence of numeric points alone. Review the reward value, breakage and accounting treatment before enabling real-value redemption. The points ledger must not silently post cashbook income or imply deposit liabilities.

## Staff-facing guarantees and release readiness

- Transactional order locks and uniqueness constraints protect earned/reversed events.
- The customer profile reports the actual ledger balance and recorded history.
- All new features are in the existing shared customer/tenant system, including standalone retail mode; no hidden bar/hotel dependency is introduced.
- Staging tests must cover payment retries, partial tenders, split refunds, rate changes, currency mismatch, verified merges, negative recovery, and two terminals finishing the same sale concurrently.
- Database migrations, PostgreSQL RLS, finance postings and real device/browser flows are **not certified** by this document; those checks belong to the deferred release verification phase.

References:
- [Django transaction documentation](https://docs.djangoproject.com/en/5.2/topics/db/transactions/)
- [Django select_for_update reference](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update)
- [Yotpo — points on refunded orders](https://support.yotpo.com/docs/point-balance-for-refunded-orders)
- [IFRS 15 revenue recognition](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-15-revenue-from-contracts-with-customers/)
