# Codex Skills Bootstrap

This repository stores project-local Codex skills so they can be reused on another machine.

## Files
- `codex/skills/` - tracked skill definitions
- `scripts/install_codex_skills.ps1` - installs the skills to `%USERPROFILE%\\.codex\\skills`

## Usage (PowerShell)
Copy mode (safe default):
`powershell -ExecutionPolicy Bypass -File .\\scripts\\install_codex_skills.ps1`

Symlink mode (single source of truth in repo):
`powershell -ExecutionPolicy Bypass -File .\\scripts\\install_codex_skills.ps1 -UseSymlink -Force`

Notes:
- `-UseSymlink` creates a junction from `%USERPROFILE%\\.codex\\skills` to `.\\codex\\skills`.
- `-Force` replaces existing `%USERPROFILE%\\.codex\\skills`.

