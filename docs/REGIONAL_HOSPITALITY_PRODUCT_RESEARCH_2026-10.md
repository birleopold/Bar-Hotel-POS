# Regional Hospitality Product Research — Uganda & East Africa

**Research date:** 15 October 2026  
**Repository reviewed:** `birleopold/Bar-Hotel-POS`, `main` at `917aba6a123e45bba537b10d4dddc3b32f7d870b` (6 October 2026)  
**Purpose:** Translate current regulatory guidance, public market signals, regional product patterns, and the source repository into a practical improvement and verification plan. This is product/engineering research, not legal or tax advice.

## Executive conclusion

The strongest route to a trusted Uganda-first, East Africa-ready hospitality platform is **operational reliability and provable control**, not simply a larger feature list. The product already has meaningful foundations: a Django modular monolith, server-rendered staff workspaces, tenant/branch/outlet scoping, POS and lodging domains, register attribution, cash movement and handover controls, an exception centre, and a shared customer identity foundation.

The next gains should come from completing those workflows end to end and proving them against real operating conditions:

1. Finish the in-progress shared customer/guest phase, including API parity, currency-correct spend, folio balances, invoice/receipt history, and privacy/retention controls.
2. Treat EFRIS and mobile money as provider integrations requiring sandbox, reconciliation, retry, and production evidence—not as configuration switches that imply certification.
3. Complete inventory/purchasing controls, business-date/night-audit operations, housekeeping and kitchen production workflows.
4. Establish repeatable SQLite, PostgreSQL/RLS/concurrency, browser, deployment, backup/restore, and physical-device evidence.
5. Make onboarding, reporting, support, data export, and pricing transparent enough for small independent venues and multi-property groups.

Do not replace the agreed Django modular monolith, template-first UI, and direct-VPS deployment with microservices, a React rewrite, Kubernetes, or premature native apps. Those changes do not address the immediate product risks.

## 1. Evidence and market signals

### Uganda hospitality opportunity

The Ministry of Tourism, Wildlife and Antiquities' 2025 statistical reporting records **1,642,215 international tourist arrivals in 2025**, up from 1,371,895 in 2024, and tourism receipts of approximately **US$1.62 billion**. The ministry also reports 876,512 direct tourism jobs for 2024. These figures demonstrate the size and recovery of the wider tourism ecosystem; they are **not** an estimate of the addressable software market.

Source: [Ministry of Tourism — Statistical Abstract 2025 / tourism statistics](https://www.tourism.go.ug/statistics/?comp-ko8ixw34_page=2&comp-kps6fu6e_page=2).

### What local vendors publicly emphasize

A scan of public product pages in October 2026 shows recurring market messages:

- **Staylly:** offline-first operations, multi-property reporting, bookings and folios, F&B POS/KDS, housekeeping, stock, mobile-money reconciliation and reports.
- **NodePoint:** UGX/local tax presentation, MTN MoMo and Airtel Money as separate tenders, offline operation, branch stock and purchase workflows.
- **ZentroApp:** EFRIS messaging, offline capability, multi-branch POS/inventory and local pricing.
- **CranePOS:** a fiscalised plan advertised with native EFRIS, electronic receipts, credit/debit notes and tax-related functions.
- **TheHotelManager:** cloud PMS positioning for hotels, lodges, apartments and short-stay properties.

Sources: [Staylly modules](https://staylly.com/modules), [NodePoint Uganda](https://www.nodepoint.africa/ug), [ZentroApp](https://www.zentroapp.app/), [CranePOS pricing](https://cranepos.com/pricing), [TheHotelManager](https://thehotelmanager.net/).

**Interpretation limit:** These are vendor-published feature claims, not independent performance tests or confirmation of current customer outcomes. They are useful for identifying buyer expectations, not for declaring any vendor superior. Bar-Hotel-POS should differentiate with reproducible reconciliation, auditable workflows, validated integrations, clear data ownership/export, and real support—not unverified marketing claims.

## 2. Regulatory and integration research

### Uganda: EFRIS is a product-critical workstream

URA's current public guidance states that all VAT-registered taxpayers must use EFRIS. URA's notice published in August 2026 also lists 12 additional sectors, including **Accommodation and Food Service Activities**, with an effective date of 1 July 2025. The notice says small businesses in those listed sectors with annual turnover below UGX 10,000,000 may be exempt from mandatory issuance but may use EFRIS voluntarily; it separately describes a rental-income threshold. Taxpayer applicability should be determined for each business with current URA guidance or a qualified tax adviser.

EFRIS documents include e-invoices, e-receipts, credit notes and debit notes. URA identifies the Fiscal Document Number (FDN), verification code and QR code as common document features. The handbook describes system-to-system API integration for computerized POS/accounting systems and says the URA EFRIS app and desktop client can operate offline for up to five days. The product must not treat that as permission for an unbounded offline fiscal queue.

Sources: [URA EFRIS Handbook](https://ura.go.ug/en/efris-handbook/), [URA — Additional Taxpayers Required to Use EFRIS (published August 2026)](https://ura.go.ug/en/additional-taxpayers-required-to-use-efris/), [URA — Invoice/Receipt Issuance](https://ura.go.ug/en/efris/invoice-receipt-issuance/).

**Implications for this codebase:**

- The existing EFRIS queue/adapter should remain honestly labelled as an integration shell until the actual current URA specifications, credentials, sandbox tests, required accreditation/certification and production acceptance are evidenced.
- Model fiscal state explicitly: not required / configured / queued / submitted / accepted / rejected / correction required / retry due. Keep provider references and error codes, but redact secrets and sensitive payloads from normal UI and logs.
- Do not print a normal POS receipt as if it were a fiscal e-receipt. Display FDN/verification/QR only when returned or generated through the valid fiscal process.
- Implement credit/debit note or correction paths linked to the original fiscal document. A local POS refund alone must not be described as an EFRIS credit note.
- Enforce retry idempotency and queue-age warnings. Provide a visible escalation before the applicable offline limit is reached.
- Make applicability configurable by tenant and business category, while avoiding a blanket claim that every small bar, hotel or restaurant has identical obligations.

### Uganda: mobile-money payments need settlement-grade accounting

The Bank of Uganda publishes the supervised payment service provider/operator directory and identifies MTN Mobile Money Uganda and Airtel Mobile Commerce Uganda among the listed providers. MTN's Open API documentation describes collections, disbursements, transaction-status checking and account-related endpoints, subject to its onboarding, KYC and commercial requirements.

Sources: [Bank of Uganda — Financial Infrastructure and Innovation](https://bou.or.ug/financial_infrastructure_innovation), [MTN Uganda — Open API](https://www.mtn.co.ug/helppersonal/mtn-open-api/), [MTN MoMo developer portal](https://momoapi.mtn.com/).

**Implications:**

- Model MTN MoMo, Airtel Money, cash, card, bank transfer and room-charge as distinct tender types where appropriate. A tender label alone is not a provider integration.
- Use a provider adapter boundary, signed/authenticated callbacks where supported, transaction-status reconciliation, idempotency keys, duplicate-callback protection, and a settlement/statement reconciliation workflow.
- Separate “payment requested”, “provider pending”, “provider confirmed”, “failed/expired”, “reversed”, and “reconciled”. Never mark a payment paid solely because a request was sent or a callback was received without validating its authenticity and transaction identity.
- Do not store mobile-money PINs. Do not store raw cardholder data; use a suitable payment provider/hosted flow if card acceptance is introduced.

### Personal data: PDPO readiness is urgent

Uganda's Data Protection and Privacy Act applies to collecting, processing, holding or using personal data within Uganda, and the PDPO's registration guidance says data collectors, controllers and processors must register unless an exemption applies. The PDPO's public information centre announced an **annual data protection and privacy compliance report deadline of 23 November 2026** for registered entities. The platform stores guest/customer contact details, preferences and notes, so roles, retention, rights requests, data access and breach evidence should be treated as core operations.

Sources: [Data Protection and Privacy Act (ULII)](https://ulii.org/en/akn/ug/act/2019/9/eng%402023-12-31), [PDPO registration classification and guidance](https://pdpo.go.ug/media//2022/01/20102021105143-Registration_Classification_and_Guidance_Notes.pdf), [PDPO information centre](https://pdpo.go.ug/knowledge-center?resourceId=1faaec8c-c601-4fa9-b65b-b02510a3cfaf).

**Implications:**

- Clarify the controller/processor relationship between the software operator and each tenant in contracts and notices; confirm the operator's own registration/reporting obligations with PDPO or counsel.
- Add privacy request handling, data export, restriction, correction, retention/deletion policy, and an auditable record of decisions.
- Keep historical financial records immutable where legal/accounting retention requires it, but do not assume that preserving a transaction snapshot automatically resolves a data-subject deletion request. Define an approved policy for profile fields versus legally retained records.
- Reduce free-text collection, warn staff not to record sensitive information unnecessarily, scope customer visibility to authorized branches/outlets, and redact personal data from logs and exports.
- Define data residency/cross-border hosting and backup retention deliberately; document subprocessors and breach-response responsibilities.

### East Africa: country-specific fiscal adapters, not one generic tax toggle

- **Kenya:** KRA describes eTIMS system-to-system integration through an API using Virtual Sales Control Unit (VSCU) or Online Sales Control Unit (OSCU), with a development, testing, vetting and certification process for third-party integrators. [KRA eTIMS](https://www.kra.go.ke/online-services/etims), [KRA system-to-system integration](https://www.kra.go.ke/business/etims-electronic-tax-invoice-management-system/learn-about-etims/etims-system-to-system-integration).
- **Rwanda:** RRA publishes EBM options for supported desktop/tablet and Android use, and describes approval/certification for integration. [RRA — About EBM](https://www.rra.gov.rw/en/about-ebm).
- **Tanzania:** the National Audit Office of Tanzania's April 2025 performance audit discusses the administration of electronic fiscal devices and EFDMS, including gaps in registration and stock/transaction coverage. This is a reminder that regional rollout needs country-specific technical and operational discovery, not a claim that Tanzania uses the same integration contract as Uganda. [NAOT — Electronic Fiscal Devices audit](https://www.nao.go.tz/reports/view/performance-audit-report-on-the-administration-of-electronic-fiscal-devices).

**Architecture recommendation:** keep a shared fiscal-document domain and separate country adapters, credentials, document formats, offline rules, cancellation/correction workflows and certification evidence. Do not implement Kenya, Rwanda or Tanzania by copying Uganda's EFRIS payloads or merely changing a country code.

## 3. Engineering standards and verification

OWASP Application Security Verification Standard **5.0.0** provides a versioned, testable set of application-security requirements. Use it as a verification checklist—initially with a documented risk-based scope covering authentication/session handling, access control, tenant isolation, input/output handling, API security, secrets, logging, file uploads and security configuration. Do not claim an ASVS level without evidence.

Sources: [OWASP ASVS 5.0.0](https://owasp.org/www-project-application-security-verification-standard/), [ASVS 5.0.0 specification](https://github.com/OWASP/ASVS/blob/master/5.0/en/0x01-Frontispiece.md).

The repository has no checked-in GitHub Actions workflow and no recorded Actions runs at the research checkpoint. A fast SQLite workflow is being introduced on this branch to automate Django checks, migration-drift detection and the local test suite. **This is only a baseline CI gate.** It does not replace:
- PostgreSQL-only locking and RLS tests using a restricted database role;
- real browser review at desktop, tablet and phone widths;
- hardware tests for printers, cash drawers, scanners and kitchen displays;
- EFRIS/provider sandbox and production acceptance;
- backup restoration, deployment smoke tests and rollback review.

The current documented stack is Django 5, DRF, templates/Bootstrap, SQLite for local development, PostgreSQL with optional RLS in production, and optional Redis/Channels/Celery. Preserve this modular monolith and shared domain services. The lack of a lockfile also means dependency resolution is not fully reproducible; introduce reviewed dependency pinning as a later engineering task rather than pinning versions without a tested compatibility run.

## 4. Source-level product review

### Foundations to preserve

- Role-specific staff workspaces and shared server-rendered UI.
- Tenant/branch/outlet scoping, workstation identity, browser pairing and revocation.
- Per-till payment/refund attribution, cash movement ledger, formal handover and manager exception review.
- Shared customer identity with explicit links to reservations, folios, POS orders and events.
- Existing shared services for orders, payments, returns, folio settlement, receiving and stock movements.
- Explicit historical-data preservation; no silent financial or stock backfill.

### Phase 05 is still the next product dependency

The authoritative `docs/SUITE_IMPLEMENTATION_TODO.md` records Phase 05 as in progress. The customer model currently stores name, email, phone, preferences and notes, but the API router has no customer endpoint. Spend, credit/folio balances, invoices, privacy/retention, cross-site scope review, and PostgreSQL/browser evidence remain open.

One source-level scope concern requires targeted regression tests before expanding the API: `visible_customers()` currently includes `Q(created_by=user)` for non-owner/admin staff in addition to records linked to their accessible sites/outlets. Because a customer record has no explicit originating site/outlet, an unlinked record created by a user can remain visible even after their site assignment changes. Review the intended policy and fix or constrain it before exposing customer data through additional API surfaces.

The spend/credit implementation must not simply sum order totals and folio charges together: room-charged POS orders can appear in both operational histories. Compute financial views from clearly defined source ledgers, preserve currency boundaries, account for refunds and voids, and explain what is included. Do not invent historical links or silently backfill money.

### Roadmap status from the authoritative checklist

| Workstream | Research assessment | Next evidence required |
| --- | --- | --- |
| Shared customers/guests (05) | In progress | API parity, privacy policy, correct spend/folio calculations, cross-site tests |
| Loyalty (06) | Pending | Idempotent points ledger, reversals and refund rules |
| Inventory intelligence / expiry (07–08) | Pending | Aging, velocity, safety stock, batches, FEFO and expiry/recall tests |
| Purchasing (09) | Pending | Full PO → partial receipt → invoice/payable → payment/credit-note lifecycle |
| Business date / night audit (10–11) | Pending | Timezone/closing-boundary rules, idempotent room posting and reconciliation |
| Housekeeping / KDS / events (12–14) | Pending | Real staff journeys, routing, timers, resource conflict tests |
| Hardware / offline / EFRIS (15–17) | Pending | Real device/provider evidence, bounded queue and conflict recovery |
| Analytics / reports / permissions / approvals (18–22) | Pending | Shared service logic, scope parity, auditable exact-action approval |
| UI discovery / notifications (23–26) | Pending | Keyboard/touch/accessibility and responsive browser evidence |
| Onboarding / demo / entitlements (27–29) | Pending | Self-serve setup, isolated demo mode, server-side module enforcement |
| Documentation / release / finance / operations (30–34) | In progress or pending | Feature matrix, release evidence, historical corrections, restore drill and source policy |

The checklist remains authoritative; this table does not mark any work item complete.

## 5. Recommended delivery sequence

### First: complete the shared customer phase

1. Review and test customer visibility rules for owner/admin, site manager, outlet manager and front desk.
2. Add customer API endpoints only through the existing authorization/service patterns; enforce tenant and branch scope for list, detail, create and update.
3. Define spend by currency from payment/refund sources; show folio charges, settlements and outstanding balance separately. Prevent double-counting room-charged orders.
4. Add invoice/receipt links only where a real document exists; distinguish ordinary receipts from fiscal documents.
5. Implement privacy request, export, restriction and approved anonymization/retention flows with reason, actor, audit and a legal-retention policy.
6. Test cross-tenant/cross-site denial, pagination/search limits, merge concurrency, historical snapshot preservation, PostgreSQL RLS and browser flows.

### Then follow the existing checklist

- Loyalty and customer-account ledger.
- Inventory intelligence, batch/expiry/FEFO and complete purchasing.
- Business date/night audit, housekeeping, KDS and event delivery.
- Hardware adapters, bounded offline reconciliation, and verified EFRIS.
- Executive reporting, capability permissions, exact-action approvals, audit explorer, search/command palette and notifications.
- Guided onboarding, safe demos, subscription enforcement, release certification, finance/history correction policy, deployment/restore evidence and source/licensing policy.

### Add explicit acceptance evidence to each release

- No cross-tenant or unauthorized cross-site data exposure in regression tests.
- Replaying a payment, refund, receiving, fiscal submission or offline operation cannot duplicate money or stock.
- Sensitive actions have actor, timestamp, reason, approval and linked source records.
- Every financial dashboard states date window, currency, scope and source calculation.
- A release certificate distinguishes SQLite, PostgreSQL/RLS, browser, provider and hardware evidence; missing mandatory evidence must fail certification.
- A production backup is proven restorable, not merely marked successful.
- Pilot venues can export their own records in usable formats and understand how to leave the service.

## 6. Suggested measures of product quality

Establish a baseline from instrumented pilot venues, then set targets with real data rather than making arbitrary promises:

- checkout latency and successful sale completion at peak;
- duplicate/failed settlement rate and time to reconcile mobile-money statements;
- fiscal queue age, acceptance/rejection rate and correction time;
- stock variance, wastage, stock-out frequency and purchase-order lead time;
- booking conflicts, room-posting discrepancies and night-audit duration;
- cashier variance frequency and percentage of shifts with fully verified handover;
- onboarding completion time, support response/resolution time, and data-export success;
- automated test coverage of critical financial invariants, PostgreSQL/RLS, responsive browsers and restore drills.

## Sources and research limits

Primary sources used: Uganda Revenue Authority, Bank of Uganda, Uganda Personal Data Protection Office, Ministry of Tourism, Kenya Revenue Authority, Rwanda Revenue Authority, National Audit Office of Tanzania, and OWASP. Vendor pages were used only to identify publicly advertised buyer expectations. Regulations and provider specifications can change; verify current requirements with the relevant authority and provider before go-live.
