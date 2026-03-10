# Meetings Pipeline

This folder contains the local meeting processing pipeline.

## Tracked files
- process_meeting.py
- README.md

## Local-only working data (ignored by git)
- VTT/ (incoming transcripts)
- summaries/ (generated summaries)
- processed/ (already processed transcripts)
- failed/ (failed transcripts)
- run_reports/ (last run and history reports)
- processor.log

## Processing rule summary
- Input: current month folder in `VTT/YYYY-MM`
- Output language: English
- Output sections: Meeting Summary + Action Items
- Excluded sections: Decisions, Risks
- Jira output: headline suggestions only
- Uncertain items: `Needs confirmation`
