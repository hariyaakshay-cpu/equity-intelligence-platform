from __future__ import annotations

import json
from pathlib import Path

from equity_intel.acquisition.models import AcquisitionReport


def write_report(report: AcquisitionReport, output_dir: str | Path) -> tuple[Path, Path]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / f"{report.run_id}.json"
    markdown_path = directory / f"{report.run_id}.md"
    json_path.write_text(json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [f"# Equity data acquisition — {report.run_id}", "", f"- Status: **{report.status}**",
        f"- Calendar: **{report.calendar_status}** — {report.calendar_basis}",
        f"- Universe: {report.universe_count}; mapped {report.mapped_count}; unmapped {report.unmapped_count}; excluded {report.excluded_count}",
        f"- Requests: {report.requested_count}; successful {report.successful_count}; no data {report.no_data_count}; request failed {report.request_failed_count}; validation failed {report.validation_failed_count}; insufficient history {report.insufficient_history_count}",
        f"- Persisted: {report.persisted_symbol_count} symbols / {report.persisted_observation_count} observations", "",
        "## Per-symbol results", "", "| Symbol | Status | Reason | Bars | First | Last | Instrument key |", "|---|---|---|---:|---|---|---|"]
    for item in report.symbols:
        vals = [str(item.get(k) or "").replace("|", "\\|").replace("\n", " ") for k in
                ("symbol", "status", "reason", "observation_count", "first_date", "last_date", "instrument_key")]
        lines.append(f"| {vals[0]} | {vals[1]} | {vals[2]} | {vals[3]} | {vals[4]} | {vals[5]} | {vals[6]} |")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path
