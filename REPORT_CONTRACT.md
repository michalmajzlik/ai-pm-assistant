# PM AI Assistant - Report Contract v1

## 1) Scope and Data Sources

### In scope reports
1. Daily Client Standup (RetuRO) - structured text
2. Weekly Project Status (internal Sensoneo management) - structured text
3. Steering Committee Pack (client + Sensoneo senior management) - presentation

### Primary data sources
1. Jira (project, issues, releases, statuses, assignees, estimates, spent, chargeable)
2. Meeting transcripts
3. Calendar events
4. Emails

### Output language
- All outputs in English.

## 2) Shared Decision Logic

### RAG model (heuristic v1, to be refined later)
- Green:
  - No active critical blocker
  - Release confidence >= 80%
  - No major dependency at risk in next 7 days
- Amber:
  - 1 significant blocker or dependency risk
  - Release confidence 60-79%
  - Noticeable slippage risk but still recoverable
- Red:
  - Multiple blockers or unresolved critical path issue
  - Release confidence < 60%
  - High probability of milestone miss or unresolved escalation

### Capacity management model (v1)
- Unit: MD (man-days)
- Reporting dimensions:
  1. Planned MD vs. consumed MD
  2. Remaining MD
  3. MD by assignee/team
  4. MD concentration risk (single-point overload)

### Billing model (v1)
- Source: Jira standard task level
- Count only issues where:
  1. `Chargeable = True`
  2. `Actual spent` is present
- Billing summary includes:
  1. Total chargeable effort
  2. Non-chargeable effort
  3. Missing/invalid billing data flags

## 3) Report Definitions

## 3.1 Daily Client Standup (RetuRO)

### Audience
- Client-side delivery stakeholders

### Purpose
- Short operational update for previous day + next 24h + release pulse

### Required sections
1. Yesterday completed
2. Today plan
3. Blockers and risks
4. Release status (planned releases + confidence + dependencies)
5. Client actions needed

### Size
- Target: concise, 1 page equivalent

### Source window
- Last 24 hours (Jira, meetings, emails, calendar)

## 3.2 Weekly Project Status (Internal)

### Audience
- Internal Sensoneo management

### Purpose
- Delivery control, internal risks, capacity, client friction, billing quality

### Required sections
1. Executive summary (RAG)
2. Delivery status (scope/time/quality)
3. Internal issues and dependencies
4. Capacity and workload (MD)
5. Client-side issues/escalations
6. Billing snapshot (Chargeable=True + Actual spent)
7. Focus for next week

### Size
- Target: 1-2 pages equivalent

### Source window
- Last 7 days (plus trend context from previous period)

## 3.3 Steering Committee Pack

### Audience
- Senior management (both client and Sensoneo)

### Purpose
- Strategic alignment and decision support

### Required slide structure
1. Overall project health (RAG + top risks)
2. Timeline and milestones (plan vs actual)
3. Release readiness summary
4. Budget/billing snapshot
5. Decisions required
6. Next period priorities

### Format
- Presentation deck + concise speaker notes

## 4) Scheduling and Deadlines (Release-driven)

### Rule
- Planned releases are discovered from Jira release objects for project scope.
- For each unreleased release with a defined `releaseDate`, create release-day reporting output aligned to that date.

### v1 scheduling behavior
1. Daily report: generated each workday and additionally marked with release context when releaseDate is today.
2. Weekly report: generated weekly; if a releaseDate is in the same week, include explicit release readiness section.
3. Steering report: generated for each planned releaseDate (release-specific executive pack).

Note: exact run times will be finalized in automation configuration step.

## 5) Data Quality Rules

1. Missing required fields must be surfaced in a "Data quality issues" subsection.
2. Ambiguous ownership (assignee/team) must be flagged, not hidden.
3. Any inferred statement must be labeled as "inference".
4. Unknown values must be explicitly marked "Unknown" (never silently omitted).

## 6) Versioning

- This file is `v1` baseline.
- RAG thresholds and KPI formulas will be tightened after first production iterations.
