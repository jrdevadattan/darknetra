# ADR-0001: Investigator Dashboard Frontend Baseline

- **Status:** Accepted
- **Date:** 2026-08-17

## Context

DARKNETRA requires a polished, responsive investigator dashboard under a short hackathon delivery window. The approved visual foundation is `arhamkhnz/next-shadcn-admin-dashboard`.

Recreating that interface from screenshots would be slower, less faithful, and would duplicate work already available under a permissive license.

## Decision

`apps/web` will be seeded from the upstream source tree of:

- Repository: `arhamkhnz/next-shadcn-admin-dashboard`
- Pinned upstream commit: `0c668859c4fdeaa0279c951c178b965cce62a125`
- License: MIT

The initial frontend baseline inherits the upstream framework/component conventions from that pinned snapshot, including Next.js 16, React 19, TypeScript, Tailwind CSS v4, shadcn-compatible components, and its existing responsive application shell.

For charts, DARKNETRA will use **Recharts** in the initial implementation because it is already present in the pinned template. ECharts will not be added unless a later requirement cannot be met with Recharts.

### Keep and adapt

- application shell and responsive layout;
- sidebar/header navigation patterns;
- theme infrastructure;
- forms, dialogs, sheets, menus, tabs, badges and toasts;
- table and pagination patterns;
- authentication presentation patterns;
- role/permission management interaction patterns;
- accessibility behavior of retained primitives;
- loading/skeleton/error-state patterns that remain useful.

### Remove

- ecommerce;
- CRM;
- finance;
- academy;
- generic calendar;
- generic mail;
- demo chat;
- unrelated analytics/example dashboards;
- dead navigation entries;
- demo-only data and dependencies that are no longer referenced.

### DARKNETRA replacement navigation

- Overview
- Cases
- Evidence
- Entities
- Activity Candidates
- Link Analysis
- NarcoGraph
- Timeline
- Alerts
- Reports
- Emerging Trends
- Source Registry
- Users
- Roles & Permissions
- Taxonomies
- System Settings
- Audit
- System Health

Case-specific views remain nested under the selected case rather than appearing as unrelated global demo pages.

## Dependency policy

Do not blindly retain every upstream dependency. After each removed template module, run static/import/build checks and remove dependencies that are no longer referenced. Do not replace working retained components merely to reduce dependency count.

No new UI library may be introduced solely to rebuild a component already supplied by the retained template/shadcn stack.

## Attribution

The upstream MIT notice is preserved in `LICENSES/next-shadcn-admin-dashboard-MIT.txt`. If substantial source files are copied with their own copyright headers, those headers must remain intact.

## Consequences

### Positive

- high-quality dashboard UX from the first implementation milestone;
- less time spent building generic admin primitives;
- consistent component behavior across investigation screens;
- reduced charting dependency surface by standardizing on Recharts;
- reproducible template baseline through the pinned commit SHA.

### Costs

- the initial import contains many irrelevant demo modules that must be removed carefully;
- dependency pruning must follow successful build/type/lint checks rather than guesswork;
- visual similarity to the upstream template requires DARKNETRA-specific information architecture, language, data states and investigator workflows so the final product does not look like an untouched admin demo.
