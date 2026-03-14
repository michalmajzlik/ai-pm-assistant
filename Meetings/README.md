# Meetings Pipeline

This folder contains the local meeting processing pipeline.

## Tracked files
- process_meeting.py
- README.md

## Local-only working data (ignored by git)
- VTT/ (incoming transcripts)
- records/ (generated canonical meeting JSON records)
- processed/ (already processed transcripts)
- failed/ (failed transcripts)
- run_reports/ (last run and history reports)
- processor.log

## Processing rule summary
- Input: current month folder in `VTT/YYYY-MM`
- Canonical output: JSON only
- Output schema: meeting metadata + summary + action_items + decisions + risks + jira_candidates + tags
- Output language: English
- Uncertain items: `needs_confirmation = true`
- Markdown summaries are no longer the source of truth
