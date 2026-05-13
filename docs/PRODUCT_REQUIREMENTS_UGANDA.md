# Product Requirements Document

## Document Purpose
This document defines the product requirements for a Uganda-fit multi-branch platform that supports hospitality, retail, lodging, events, and services under one workspace.

This PRD focuses on operating workflows, data structure, UI language, and responsibilities.

This PRD does not yet define:

- payment gateway requirements
- mobile money integration details
- EFRIS implementation details

## Product Vision
Build one platform where a business owner can run multiple branches and multiple sections from one account, while each team still gets a screen and workflow that fits its day-to-day work.

## Business Problem
Many businesses in Uganda operate mixed services under one owner:

- hotel plus bar plus restaurant
- supermarket plus cafeteria
- lodge plus activities plus spa
- venue plus rooms plus food service

These businesses usually struggle with:

- disconnected systems
- poor visibility across sections
- weak stock control
- manual coordination between kitchen, bar, rooms, and services
- unclear responsibility by staff role

## Product Goals

### Primary goals

- unify operations under one workspace
- support multiple branches and sections
- allow one order to carry multiple line types where needed
- keep section visibility separate
- improve stock control and operational handoff
- give owners and managers clear reporting by branch and section

### Secondary goals

- simplify setup for tenant admins
- make staff screens fast and clear
- reduce training time through familiar language
- support expansion into new service lines without redesign

## Non-Goals For This Phase

- full payment rail design
- card/mobile money orchestration
- EFRIS issuance rules
- loyalty and CRM deep design
- full scheduling engine across all service types

## Target Users

### Platform Owner
Needs:

- tenant provisioning
- plan and subscription control
- product-wide visibility
- support and configuration tools

### Tenant Owner / Tenant Admin
Needs:

- branch and section setup
- staff creation and role assignment
- item and service setup
- stock and purchasing oversight
- access to high-level reports

### Manager / Supervisor
Needs:

- branch or outlet oversight
- ability to approve sensitive actions
- shift and handoff visibility
- stock and operational tracking

### Frontline Staff
Needs:

- clear task-specific screens
- simple buttons and labels
- fast order and stock workflows
- restricted access to only what is needed

## Product Structure

### Workspace Layer
Represents one business account.

Requirements:

- one workspace can have many branches
- one workspace can have many business lines
- one workspace can hold one shared team and permission model

### Branch Layer
Represents physical locations.

Requirements:

- branch setup under one workspace
- branch-specific visibility where needed
- branch-specific reports

### Section Layer
Represents operating units.

Examples:

- bar
- kitchen
- front desk
- supermarket
- spa
- event space

Requirements:

- section-aware operational routing
- section-aware visibility
- section-aware reporting

## Functional Requirements

### 1. Orders and Operational Routing

Requirements:

- system must allow one order to hold food, drinks, and services where business logic allows
- each line must route to the correct section
- staff should only see the lines relevant to their section in prep/operational views
- order close should be blocked when required prep workflow is incomplete
- ready-to-serve and handoff states must be explicit

Acceptance criteria:

- kitchen lines do not appear in bar-only view
- bar lines do not appear in kitchen-only view
- service lines can route to service sections
- order cannot close while required kitchen lines are still pending or in prep

### 2. Services and Service Packages

Requirements:

- system must support a generic service catalog
- admins must be able to create any service type without custom code
- each service can have multiple packages or variants
- each package can have its own price
- each package can optionally override duration and section routing

Examples:

- massage: Swedish, deep tissue, couples package
- sauna: normal session, VIP session
- boat ride: standard trip, sunset package

Acceptance criteria:

- new service appears automatically in staff order entry
- package selection affects price and label
- service line routes to configured section

### 3. Stock and Purchasing

Requirements:

- tracked items must support single movement entry
- tracked items must support CSV upload
- failed upload rows must generate downloadable error report
- users must be able to download a CSV template
- stock movements must support receive, adjust in, adjust out, and waste
- stock transfer between outlets must be supported
- stock counts must be supported
- purchase order receiving must be supported

Acceptance criteria:

- user can record a stock movement from UI
- user can upload CSV with valid rows
- failed rows can be downloaded as report
- no tracked items state must offer a quick item creation path

### 4. Quick Item Creation

Requirements:

- when stock movement page has no tracked items, user must not be blocked
- user must be able to create a tracked item inline
- inline create must require at least one menu category
- created item must be active and inventory-tracked immediately

Acceptance criteria:

- item can be created without leaving the stock movement page
- new item becomes selectable in stock movement flow

### 5. Lodging

Requirements:

- support reservations
- support rooms and room types
- support folios
- support guest-linked operational flow

Acceptance criteria:

- front desk screens show lodging-only workflows
- lodging setup is visible only where relevant

### 6. Events

Requirements:

- support event spaces
- support bookings
- allow event management from same workspace

Acceptance criteria:

- event staff can manage spaces and bookings without seeing unrelated modules

### 7. Team and Permissions

Requirements:

- tenant admin can create workers, invite workers, update roles, and limit scope
- users should only see pages allowed for their role
- owner and protected roles must have safety checks

Acceptance criteria:

- worker CRUD exists inside the app
- users cannot reach restricted sections outside their scope

### 8. Setup and Admin Console

Requirements:

- guided setup for new tenants
- branch and outlet setup
- item, service, and lodging setup
- service package setup
- setup state tracking

Acceptance criteria:

- tenant can complete setup from Console without Django admin
- platform owner keeps Django admin, tenant uses in-app console

## UX Requirements

### General UX principles

- action-first screens
- concise language
- clear empty states
- direct next steps when setup is incomplete
- no dead-end pages

### Page requirements

- every page must clearly indicate context: workspace, branch, outlet, property
- staff pages should show only relevant actions
- admin pages should reduce back-and-forth

### Button requirements

- button labels should be short and consistent
- use `New`, `Open`, `Save`, `Record`, `Upload`, `Transfer`, `Start`, `Close`, `Manage`
- avoid overly technical wording where a business term exists

## Reporting Requirements

Requirements:

- support section-level reporting
- support branch-level reporting
- support workspace-level reporting
- distinguish food, drinks, and services where possible
- expose stock and operational summaries

Acceptance criteria:

- owner can understand business performance by branch and section
- section revenue and activity do not get mixed together

## Data Requirements

Core entities should include:

- tenant/workspace
- branch/site
- outlet/section
- order and order line
- menu item
- service offering
- service package
- stock balance and stock movement
- purchase order
- reservation, room, folio
- event space and booking
- user, membership, role
- audit event

## Security and Access Requirements

Requirements:

- strict tenant isolation
- role-scoped access
- outlet/site scoping where needed
- audit records for sensitive actions

Acceptance criteria:

- users cannot see another tenant’s data
- users cannot operate outside assigned scope

## Rollout Priorities

### Phase 1

- core workspace and branch model
- role-scoped staff UI
- orders and section routing
- stock basics

### Phase 2

- services and service packages
- CSV stock receive
- worker management
- guided setup

### Phase 3

- deeper reporting
- stronger branch/section workflows
- improved operational dashboards

## Success Measures

- tenant admin can set up branch, outlet, items, services, and workers without Django admin
- staff can complete daily workflows with minimal training
- mixed businesses can run multiple sections under one workspace
- stock movement and service setup no longer block operations
- line routing and section reporting remain accurate

## Open Decisions For Later

- full payment design
- EFRIS issuance flow
- corporate billing rules
- loyalty and CRM scope
- deeper reservation scheduling rules for activities and services
