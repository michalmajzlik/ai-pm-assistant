#!/usr/bin/env python3
import argparse
import json
import logging
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from openai import OpenAI


BASE_DIR = Path(__file__).resolve().parent
VTT_ROOT = BASE_DIR / "VTT"
RECORD_ROOT = BASE_DIR / "records"
PROCESSED_ROOT = BASE_DIR / "processed"
FAILED_ROOT = BASE_DIR / "failed"
REPORT_ROOT = BASE_DIR / "run_reports"
LOG_FILE = BASE_DIR / "processor.log"
DEFAULT_MODEL_CANDIDATES = ["gpt-5", "gpt-5-mini", "gpt-4o-mini"]


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )


def read_vtt(path: Path) -> str:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    text = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("WEBVTT"):
            continue
        if "-->" in stripped:
            continue
        if re.fullmatch(r"\d+", stripped):
            continue
        if stripped.startswith("NOTE"):
            continue
        if re.search(r"\b(line|position|align|size):", stripped):
            continue
        text.append(stripped)
    return "\n".join(text)


def infer_meeting_date(path: Path) -> str:
    match = re.match(r"(\d{4}-\d{2}-\d{2})", path.stem)
    return match.group(1) if match else "Unknown"


def build_prompt(transcript: str, meeting_date: str, meeting_title: str) -> str:
    return f"""
Convert this meeting transcript into a single valid JSON object for execution tracking.

Return JSON only. No markdown. No code fences. No explanation.

Use exactly this schema:
{{
  "schema_version": "1.0",
  "meeting_title": "{meeting_title}",
  "meeting_date": "{meeting_date}",
  "participants": ["Name 1"],
  "summary": ["bullet 1", "bullet 2"],
  "action_items": [
    {{
      "id": "A1",
      "action": "text",
      "owner": "Unknown",
      "due_date": "Unknown",
      "priority": "High|Medium|Low",
      "status": "Open",
      "needs_confirmation": false
    }}
  ],
  "decisions": [
    {{
      "id": "D1",
      "decision": "text",
      "owner": "Unknown",
      "date": "Unknown",
      "rationale": "Unknown",
      "needs_confirmation": false
    }}
  ],
  "risks": [
    {{
      "id": "R1",
      "risk": "text",
      "impact": "High|Medium|Low|Unknown",
      "likelihood": "High|Medium|Low|Unknown",
      "mitigation": "Unknown",
      "owner": "Unknown",
      "needs_confirmation": false
    }}
  ],
  "jira_candidates": [
    {{
      "id": "J1",
      "summary": "short ticket title",
      "issue_type": "Task|Story|Bug|Unknown",
      "priority": "High|Medium|Low|Unknown",
      "assignee": "Unknown",
      "labels": ["meeting"],
      "description": "short implementation-ready description"
    }}
  ],
  "tags": ["tag1"]
}}

Rules:
- Language must be English.
- Use concise, factual wording.
- Use only evidence from transcript; do not invent facts.
- Use "Unknown" for missing scalar values.
- Use empty arrays when a section has no items.
- IDs must be sequential (A1, A2 / D1, D2 / R1, R2 / J1, J2).
- Mark uncertainty with "needs_confirmation": true.
- Keep "summary" to 5-8 concise bullets.
- "tags" should be short lowercase topic labels when strongly supported by the transcript.

Transcript:
{transcript}
""".strip()


def strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned, count=1)
        cleaned = re.sub(r"\s*```$", "", cleaned, count=1)
    return cleaned.strip()


def output_path_for(vtt_path: Path, vtt_root: Path, record_root: Path) -> Path:
    rel_parent = vtt_path.parent.relative_to(vtt_root)
    out_dir = record_root / rel_parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    return out_dir / f"{stamp}_{vtt_path.stem}.json"


def move_target_for(vtt_path: Path, vtt_root: Path, target_root: Path) -> Path:
    rel_parent = vtt_path.parent.relative_to(vtt_root)
    dst_dir = target_root / rel_parent
    dst_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    return dst_dir / f"{stamp}_{vtt_path.name}"


def collect_current_month_vtts(vtt_root: Path, month: str | None) -> list[Path]:
    selected_month = month or datetime.now().strftime("%Y-%m")
    month_dir = vtt_root / selected_month
    if not month_dir.exists():
        return []
    return sorted(month_dir.glob("*.vtt"))


def call_model_with_fallback(client: OpenAI, prompt: str, model_hint: str | None) -> str:
    models = [model_hint] if model_hint else []
    models.extend(DEFAULT_MODEL_CANDIDATES)

    last_exc: Exception | None = None
    for model in dict.fromkeys(models):
        try:
            logging.info("Trying model: %s", model)
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            return strip_code_fences(response.choices[0].message.content or "")
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logging.warning("Model %s failed: %s", model, exc)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("No model candidates available.")


def write_run_report(
    started_at: datetime,
    finished_at: datetime,
    month: str,
    processed: list[str],
    failed: list[str],
    skipped: list[str],
) -> None:
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    content = [
        "# Meeting Processor Run Report",
        f"- Started: {started_at.isoformat(timespec='seconds')}",
        f"- Finished: {finished_at.isoformat(timespec='seconds')}",
        f"- Month: {month}",
        f"- Processed: {len(processed)}",
        f"- Failed: {len(failed)}",
        f"- Skipped: {len(skipped)}",
        "",
        "## Processed Files",
    ]
    if processed:
        content.extend([f"- {item}" for item in processed])
    else:
        content.append("- None")

    content.append("")
    content.append("## Failed Files")
    if failed:
        content.extend([f"- {item}" for item in failed])
    else:
        content.append("- None")

    content.append("")
    content.append("## Skipped Files")
    if skipped:
        content.extend([f"- {item}" for item in skipped])
    else:
        content.append("- None")

    timestamped = REPORT_ROOT / f"run_report_{finished_at.strftime('%Y-%m-%d_%H%M%S')}.md"
    last_report = REPORT_ROOT / "last_run_report.md"
    text = "\n".join(content) + "\n"
    timestamped.write_text(text, encoding="utf-8")
    last_report.write_text(text, encoding="utf-8")


def normalize_record(raw_record: dict[str, Any], source_path: Path) -> dict[str, Any]:
    record = dict(raw_record)
    record["schema_version"] = str(record.get("schema_version") or "1.0")
    record["meeting_title"] = str(record.get("meeting_title") or source_path.stem)
    record["meeting_date"] = str(record.get("meeting_date") or infer_meeting_date(source_path))
    record["participants"] = [str(x).strip() for x in record.get("participants", []) if str(x).strip()] or ["Unknown"]
    record["summary"] = [str(x).strip() for x in record.get("summary", []) if str(x).strip()]
    record["action_items"] = record.get("action_items", []) if isinstance(record.get("action_items", []), list) else []
    record["decisions"] = record.get("decisions", []) if isinstance(record.get("decisions", []), list) else []
    record["risks"] = record.get("risks", []) if isinstance(record.get("risks", []), list) else []
    record["jira_candidates"] = record.get("jira_candidates", []) if isinstance(record.get("jira_candidates", []), list) else []
    record["tags"] = [str(x).strip().lower() for x in record.get("tags", []) if str(x).strip()]
    record["source_path"] = str(source_path)
    record["processed_at"] = datetime.now().isoformat(timespec="seconds")
    return record


def process_one(path: Path, client: OpenAI, vtt_root: Path, record_root: Path, model_hint: str | None) -> tuple[bool, str]:
    transcript = read_vtt(path)
    if not transcript.strip():
        return False, f"Skipped empty transcript: {path.name}"

    meeting_date = infer_meeting_date(path)
    prompt = build_prompt(transcript, meeting_date, path.stem)
    response_text = call_model_with_fallback(client, prompt, model_hint)
    record = normalize_record(json.loads(response_text), path)

    out_path = output_path_for(path, vtt_root, record_root)
    out_path.write_text(json.dumps(record, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return True, f"Processed {path.name} -> {out_path}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Process current-month meeting .vtt files into canonical JSON meeting records.")
    parser.add_argument("--month", type=str, default=None, help="Month folder in format YYYY-MM. Default is current month.")
    parser.add_argument("--vtt-root", type=Path, default=VTT_ROOT)
    parser.add_argument("--record-root", type=Path, default=RECORD_ROOT)
    parser.add_argument("--processed-root", type=Path, default=PROCESSED_ROOT)
    parser.add_argument("--failed-root", type=Path, default=FAILED_ROOT)
    parser.add_argument("--model", type=str, default=os.getenv("OPENAI_MODEL"), help="Preferred model. Fallback chain is automatic.")
    args = parser.parse_args()

    setup_logging()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logging.error("OPENAI_API_KEY is not set.")
        return 1

    selected_month = args.month or datetime.now().strftime("%Y-%m")
    args.vtt_root.mkdir(parents=True, exist_ok=True)
    args.record_root.mkdir(parents=True, exist_ok=True)
    args.processed_root.mkdir(parents=True, exist_ok=True)
    args.failed_root.mkdir(parents=True, exist_ok=True)

    vtt_files = collect_current_month_vtts(args.vtt_root, selected_month)
    if not vtt_files:
        logging.info("No new .vtt files found in %s for month %s", args.vtt_root, selected_month)
        return 0

    client = OpenAI(api_key=api_key)
    started_at = datetime.now()
    processed: list[str] = []
    failed: list[str] = []
    skipped: list[str] = []

    for path in vtt_files:
        try:
            ok, msg = process_one(path, client, args.vtt_root, args.record_root, args.model)
            if ok:
                target = move_target_for(path, args.vtt_root, args.processed_root)
                shutil.move(str(path), str(target))
                processed.append(path.name)
                logging.info(msg)
            else:
                skipped.append(path.name)
                logging.info(msg)
        except Exception as exc:  # noqa: BLE001
            fail_target = move_target_for(path, args.vtt_root, args.failed_root)
            try:
                shutil.move(str(path), str(fail_target))
            except Exception:  # noqa: BLE001
                logging.exception("Could not move failed file %s", path)
            failed.append(f"{path.name}: {exc}")
            logging.exception("Failed processing %s", path.name)

    finished_at = datetime.now()
    write_run_report(started_at, finished_at, selected_month, processed, failed, skipped)
    logging.info("Run finished. Processed=%s Failed=%s Skipped=%s", len(processed), len(failed), len(skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
