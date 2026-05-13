# UI Terminology Guide

## Purpose
This guide defines the preferred page names, button labels, and common UI terms for the app.

The goal is to keep language:

- clear
- practical
- consistent
- suitable for Uganda business operations

This guide should be used across:

- Staff app
- Console app
- setup flows
- buttons
- empty states
- alerts and success messages

## Core Principles

### Use business language, not system language
Prefer terms users already understand from daily work.

Use:

- branch
- section
- till
- stock receive
- stock take
- room charge
- shift close

Avoid when possible:

- tenant
- entity
- terminal context
- inventory mutation
- operational module

### Use action-first labels
Buttons should clearly say what will happen.

Good:

- `New order`
- `Record stock`
- `Upload CSV`
- `Start stock count`
- `Create item`

Avoid:

- `Submit`
- `Process`
- `Execute`
- `Proceed`

### Prefer one term per concept
Do not switch between multiple labels for the same thing.

Examples:

- use `Branch`, not branch on one page and property on another unless lodging specifically requires property
- use `Section` for operational area
- use `Services`, not services on one page and experiences on another unless it is a deliberate business-facing label

## Global Preferred Terms

| Concept | Preferred Term | Notes |
|---|---|---|
| Tenant | Workspace | Use `tenant` in code, `workspace` in UI |
| Site | Branch or Property | Use `Property` for lodging contexts, `Branch` in general business context |
| Outlet | Section | Keep `outlet` in code and admin detail where needed, but prefer `section` in user-facing operational language |
| Membership role | Role | Short and clear |
| KDS | Prep queue | More readable for staff |
| Folio | Folio | Keep for lodging users; add small help text where needed |
| Stock movement | Stock movement | Good existing term |
| Stock count | Stock take / stock count | `Stock count` is fine in UI, `stock take` acceptable in help text |
| Purchase order | Purchase order | Standard and understood |
| Service offering | Service | Simpler for UI |
| Service option | Package | Better for massage, sauna, boat ride, etc. |

## Staff App Navigation

### Current major pages
Use these preferred labels.

| Current Area | Preferred Label |
|---|---|
| Home | Home |
| Orders | Orders |
| Tables | Tables |
| Kitchen | Prep queue |
| Menu | Items |
| Promotions | Offers |
| Sales | Sales |
| Inventory | Stock |
| Purchasing | Purchasing |
| Workspace | Workspace |
| Reservations | Reservations |
| Folios | Folios |
| Rooms | Rooms |
| Types | Room types |
| Events | Events |

### Notes

- `Kitchen` in top nav should eventually become `Prep queue`
- `Menu` should eventually become `Items`
- `Promotions` should eventually become `Offers`
- `Inventory` should eventually become `Stock`

## Console App Navigation

| Current Area | Preferred Label |
|---|---|
| Admin console | Admin console |
| Organization | Business setup |
| Guided setup | Guided setup |
| Properties & outlets | Branches & sections |
| Menu categories | Item categories |
| Menu items | Items |
| Services | Services |
| Room types | Room types |
| Rooms | Rooms |
| Nightly rates | Room rates |
| Platform | Platform |
| Manage workspaces | Manage workspaces |

### Notes

- `Organization` is acceptable in Console, but `Business setup` is friendlier in headings and summaries
- `Properties & outlets` is accurate but can become `Branches & sections` for general use

## Orders and Service Language

### Preferred labels

| Current / Technical | Preferred UI Label |
|---|---|
| Order detail | Order |
| Held tab | Held tab |
| Walk-in | Walk-in |
| Acknowledge ready | Confirm handoff |
| KDS status | Prep status |
| Ready to serve | Ready for serving |
| Handoff acknowledged | Handoff confirmed |
| Void line | Remove line |
| Void order | Cancel order |

### Notes

- Use `Remove line` only if business meaning is still clear; keep `Void` where audit importance matters
- `Confirm handoff` is clearer than `Acknowledge ready`

## Stock and Purchasing Language

### Preferred page labels

| Current | Preferred |
|---|---|
| Inventory | Stock |
| Stock ledger | Stock ledger |
| Record movement | Record stock movement |
| Upload CSV | Upload stock CSV |
| Transfer | Transfer stock |
| Stock counts | Stock counts |
| Balances | Stock balances |

### Preferred button labels

| Current | Preferred |
|---|---|
| Record movement | Record stock |
| Save | Save |
| Upload | Upload CSV |
| Download CSV template | Download CSV template |
| Download error report | Download error report |
| Download last error report | Download last error report |
| Start stock count | Start stock count |
| Complete | Complete stock count |

### Stock reason terms

| System Term | Preferred UI Term |
|---|---|
| Receive / purchase | Stock receive |
| Adjustment increase | Increase stock |
| Adjustment decrease | Reduce stock |
| Waste / shrink | Waste / breakage |

## Lodging Language

| Current | Preferred |
|---|---|
| Reservations | Reservations |
| Folios | Folios |
| Rooms | Rooms |
| Room types / Types | Room types |
| Nightly rates | Room rates |
| Charge to folio | Charge to room |

### Notes

- `Charge to room` is more familiar than `Post to folio` for many users
- keep `folio` as the back-office term on folio pages

## Services Language

| Current / Technical | Preferred |
|---|---|
| Service offering | Service |
| Service option | Package |
| Duration minutes | Duration |
| KDS station | Service section |

### Examples

- `Massage` -> service
- `Deep tissue 90 min` -> package
- `Boat ride` -> service
- `Sunset package` -> package

## Team and Workspace Language

| Current | Preferred |
|---|---|
| Members | Team members |
| New worker | New worker |
| Invite recovery | Invite recovery |
| Branding | Branding |
| Modules | Modules |
| Integrations | Integrations |
| Activity log / Audit | Activity log |

### Preferred action labels

- `New worker`
- `Invite worker`
- `Manage member`
- `Deactivate worker`
- `Bulk update`
- `Regenerate invite`

## Button Style Rules

### Use `New` for creation screens
Preferred:

- `New order`
- `New worker`
- `New supplier`
- `New purchase order`
- `New reservation`
- `New service`
- `New package`

### Use `Create` inside inline or modal actions
Preferred:

- `Create item`
- `Create tracked item`
- `Create category`

### Use `Open` for navigation into an area
Preferred:

- `Open guided setup`
- `Open items`
- `Open organization`

### Use `Record` for operational entries
Preferred:

- `Record stock`
- `Record refund`
- `Record payment`

### Use `Manage` for settings or admin pages
Preferred:

- `Manage packages`
- `Manage workspaces`
- `Manage members`

## Empty-State Language

### Good empty-state patterns

- `No tracked items yet. Create one and start recording stock.`
- `No services yet. Add your first service to start selling packages and sessions.`
- `No branches yet. Open guided setup to create your first branch.`
- `No workers yet. Add your first worker to start assigning roles.`
- `No purchase orders yet. Create one when you are ready to receive stock.`

### Avoid

- `No records found`
- `No data available`
- `There are currently no entries`

## Message Tone

### Preferred success messages

- `Tracked item created: Bath robe`
- `Stock movement recorded`
- `Service added`
- `Package saved`
- `Handoff confirmed`

### Preferred blocking messages

- `Create at least one active category first before adding tracked items.`
- `Order cannot be closed yet: kitchen food items are still pending.`
- `No tracked items are available for stock movement yet.`

### Avoid

- overly technical API wording
- raw validation dumps
- backend-only vocabulary

## Recommended Future Renames
These are recommended UI-facing renames for future polish.

| Current Label | Recommended Label |
|---|---|
| Kitchen | Prep queue |
| Menu | Items |
| Promotions | Offers |
| Inventory | Stock |
| Record movement | Record stock |
| Service offering | Service |
| Service option | Package |
| Organization | Business setup |
| Properties & outlets | Branches & sections |

## Usage Rule
When in doubt:

1. choose the shorter label
2. choose the business term over the technical term
3. keep the same term everywhere once chosen
4. prefer clarity for frontline staff over internal architecture accuracy
