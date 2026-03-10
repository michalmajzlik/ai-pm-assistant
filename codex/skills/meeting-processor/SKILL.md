---
name: "meeting-processor"
description: "Process meeting transcripts into project-management outputs. Use when a user asks to summarize a meeting, extract action items, capture decisions, identify risks, or propose Jira tasks from meeting notes/transcripts (including long transcripts that require chunking first)."
---

# Meeting Processor

Process the provided meeting transcript and return structured markdown optimized for project execution.

## Inputs

Expect one transcript in plain text, Markdown, VTT-derived text, or mixed notes. If metadata exists (date, attendees, project), preserve it.

## Workflow

1. Clean the transcript.
- Remove obvious filler noise and duplicated lines.
- Keep meaning-bearing statements, commitments, blockers, and decisions.

2. Detect transcript length.
- Treat as long when it is too large to reason about reliably in one pass.
- For long transcripts, split into sections before full extraction.

3. Split long transcripts first.
- Prefer natural boundaries in this order: explicit agenda sections, topic shifts, speaker/time blocks.
- If no clear boundaries, chunk by contiguous blocks of similar size.
- Process each section independently for summary, actions, decisions, and risks.
- Merge section outputs and deduplicate overlaps.

4. Extract core outputs.
- Infer only what is strongly supported by transcript evidence.
- Mark uncertain items as `Needs confirmation`.
- Normalize action items with owner and due date when available.

5. Suggest Jira tasks.
- Convert actionable engineering/product work into task candidates.
- Group duplicates and split oversized work into smaller tasks.
- For each suggested task, include enough detail for immediate ticket creation.

## Output Format

Return exactly this structure:

```markdown
# Meeting Summary
- Date: <date or Unknown>
- Participants: <list or Unknown>
- High-level summary: <5-8 bullets>

# Action Items
| ID | Action | Owner | Due Date | Priority | Status | Source Section |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | ... | ... | ... | High/Medium/Low | Open | S1 |

# Decisions
| ID | Decision | Owner/Driver | Date | Rationale | Source Section |
| --- | --- | --- | --- | --- | --- |
| D1 | ... | ... | ... | ... | S2 |

# Risks
| ID | Risk | Impact | Likelihood | Mitigation | Owner | Source Section |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | ... | High/Medium/Low | High/Medium/Low | ... | ... | S3 |

# Jira Task Suggestions
| ID | Suggested Issue Type | Summary | Description | Assignee | Priority | Labels | Dependencies |
| --- | --- | --- | --- | --- | --- | --- | --- |
| J1 | Story/Task/Bug | ... | ... | ... | ... | ... | ... |
```

## Quality Rules

- Use concise, concrete language.
- Do not invent attendees, owners, dates, or commitments.
- If information is missing, write `Unknown`.
- Keep IDs stable and sequential (`A1`, `D1`, `R1`, `J1`).
- Preserve traceability using `Source Section` references (`S1`, `S2`, ...).
- If no items exist for a section, keep the heading and write `- None identified`.

## Long Transcript Handling Notes

When chunking is used, include section labels (`S1`, `S2`, ...) internally during processing and map every extracted row back to at least one section. Merge contradictory statements by favoring the most recent explicit statement and note ambiguity as `Needs confirmation`.