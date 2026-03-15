# Project Config Templates

These templates define local project-specific report behavior for the generic PM AI assistant.

## Built-in default profiles
- `software_delivery`: best default for most software projects. Weekly report uses `Delivery`, `Scope and estimation`, and `Budget`.
- `multi_workstream`: use when the project has two named delivery streams/workstreams. Rename the default sections after setup.
- `managed_service`: use when the project mixes operations/support with planned delivery.

## Setup questions a human or Claude Code should ask
1. What is the Jira project key?
2. What project display name should appear in reports?
3. Which default profile fits best?
4. If `multi_workstream` is used, what should the two workstream sections be called?
5. Which keywords identify each weekly status section in Jira issue summaries or release names?
6. Do you want to keep the default daily and steering report labels, or rename them?

## Git safety
Actual project configs should stay local in `%APPDATA%\AIPMAssistant\project_report_config.json`.
They are intentionally not stored in the repository.
