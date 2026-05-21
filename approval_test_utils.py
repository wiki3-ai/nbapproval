import json
import html
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import ipywidgets as widgets
from IPython.display import display

_APPROVAL_LAST_ACTUAL = {}
_APPROVAL_RECORDS = {}
_TEST_NOTEBOOK_PATH = None
_APPROVALS_NOTEBOOK_PATH = None


def configure_approval_store(test_notebook_path=None, approvals_notebook_path=None):
    global _TEST_NOTEBOOK_PATH, _APPROVALS_NOTEBOOK_PATH
    _TEST_NOTEBOOK_PATH = test_notebook_path
    _APPROVALS_NOTEBOOK_PATH = approvals_notebook_path


def stable_records(records, sort_by):
    if not sort_by:
        return records
    frame = pd.DataFrame(records)
    return frame.sort_values(sort_by).reset_index(drop=True).to_dict("records")


def to_iso_records(frame):
    normalized = frame.copy()
    for col in normalized.columns:
        if pd.api.types.is_datetime64_any_dtype(normalized[col]):
            normalized[col] = normalized[col].dt.strftime("%Y-%m-%d")
    return normalized.to_dict("records")


def _normalize_cell_id(value):
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "-", str(value)).strip("-")
    return (cleaned or "approval-test")[:64]


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _resolve_tests_notebook_path():
    if _TEST_NOTEBOOK_PATH:
        return Path(_TEST_NOTEBOOK_PATH).resolve()
    return None


def _resolve_approvals_notebook_path():
    if _APPROVALS_NOTEBOOK_PATH:
        return Path(_APPROVALS_NOTEBOOK_PATH).resolve()

    tests_nb = _resolve_tests_notebook_path()
    if tests_nb is not None:
        return tests_nb.parent / "__approvals__" / tests_nb.name

    return Path.cwd() / "__approvals__" / "approvals.ipynb"


def _empty_notebook():
    return {
        "cells": [],
        "metadata": {
            "language_info": {"name": "python"},
            "approval_store": {"format": "raw-cell-per-test"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def _make_raw_approval_cell(test_id, record, created_at=None, updated_at=None):
    metadata = {
        "language": "raw",
        "approval_test_id": test_id,
    }
    if created_at:
        metadata["created_at"] = created_at
    if updated_at:
        metadata["updated_at"] = updated_at
    return {
        "cell_type": "raw",
        "id": _normalize_cell_id(test_id),
        "metadata": metadata,
        "source": [json.dumps(record, indent=2, ensure_ascii=True)],
    }


def _parse_cell_json_value(cell):
    source = cell.get("source", "")
    if isinstance(source, list):
        source = "".join(source)
    try:
        return json.loads(source)
    except Exception:
        return None


def _read_approvals_notebook():
    path = _resolve_approvals_notebook_path()
    if not path.exists():
        return _empty_notebook()
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_approvals_notebook(nb):
    path = _resolve_approvals_notebook_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(nb, f, indent=4, ensure_ascii=True)


def _normalize_record(test_id, parsed_value):
    def _normalize_decision(value):
        if value is None:
            return None
        text = str(value).strip().lower()
        if text in {"approved", "confirm", "confirmed"}:
            return "Approved"
        if text in {"disapproved", "deny", "denied"}:
            return "Disapproved"
        return None

    if isinstance(parsed_value, dict) and (
        "approved" in parsed_value or "decision" in parsed_value or "test_id" in parsed_value
    ):
        record = {
            "test_id": parsed_value.get("test_id") or test_id,
            "approved": parsed_value.get("approved"),
            "decision": _normalize_decision(parsed_value.get("decision")),
        }
    else:
        record = {
            "test_id": test_id,
            "approved": parsed_value,
            "decision": "Approved" if parsed_value is not None else None,
        }
    return record


def _coerce_raw_cells_with_test_ids(nb):
    changed = False
    normalized_cells = []
    for cell in nb.get("cells", []):
        parsed = _parse_cell_json_value(cell)
        if parsed is None:
            continue
        metadata = cell.get("metadata", {})
        test_id = metadata.get("approval_test_id") or str(cell.get("id", ""))
        if not test_id or test_id.startswith("#VSC-"):
            continue
        record = _normalize_record(test_id, parsed)
        created_at = metadata.get("created_at") or _utc_now_iso()
        updated_at = metadata.get("updated_at")
        normalized = _make_raw_approval_cell(test_id, record, created_at=created_at, updated_at=updated_at)
        if (
            cell.get("cell_type") != "raw"
            or metadata.get("approval_test_id") != test_id
            or cell.get("id") != normalized["id"]
        ):
            changed = True
        normalized_cells.append(normalized)
    nb["cells"] = normalized_cells
    return nb, changed


def load_approval_records():
    nb = _read_approvals_notebook()
    nb, changed = _coerce_raw_cells_with_test_ids(nb)
    if changed:
        _write_approvals_notebook(nb)
    records = {}
    for cell in nb.get("cells", []):
        test_id = cell.get("metadata", {}).get("approval_test_id")
        parsed = _parse_cell_json_value(cell)
        if not test_id or parsed is None:
            continue
        records[test_id] = _normalize_record(test_id, parsed)
    return records


def save_approval_record(test_id, record):
    nb = _read_approvals_notebook()
    nb, _ = _coerce_raw_cells_with_test_ids(nb)
    now = _utc_now_iso()
    updated = False
    for i, cell in enumerate(nb.get("cells", [])):
        existing_id = cell.get("metadata", {}).get("approval_test_id")
        if existing_id == test_id:
            created_at = cell.get("metadata", {}).get("created_at") or now
            nb["cells"][i] = _make_raw_approval_cell(
                test_id,
                record,
                created_at=created_at,
                updated_at=now,
            )
            updated = True
            break
    if not updated:
        nb.setdefault("cells", []).append(_make_raw_approval_cell(test_id, record, created_at=now))
    _write_approvals_notebook(nb)


class ApprovalTest:
    def __init__(self, test_id, description, actual, approved=None, decision=None, context=None):
        self.test_id = test_id
        self.description = description
        self.context = context or {"@vocab": "https://schema.org/"}
        self.actual = actual
        self.approved = approved
        self.decision = decision

        self.has_approved = approved is not None
        self.matches = self.has_approved and approved == actual

        if decision == "Disapproved":
            self.passed = False
            self.status = "Disapproved"
        elif not self.has_approved:
            self.passed = False
            self.status = "missing-approved"
        elif self.matches:
            self.passed = True
            self.status = "Approved"
        else:
            self.passed = False
            self.status = "changed"

        if not self.has_approved or self.matches:
            self.diff = []
        else:
            self.diff = {"approved": approved, "actual": actual}

    def _jsonld_payload(self):
        return {
            "@context": self.context,
            "@type": "PropertyValue",
            "name": self.test_id,
            "description": self.description,
            "value": self.actual,
            "expectedValue": self.approved,
            "result": self.passed,
            "additionalProperty": [
                {"@type": "PropertyValue", "name": "status", "value": self.status},
                {"@type": "PropertyValue", "name": "decision", "value": self.decision},
                {"@type": "PropertyValue", "name": "diff", "value": self.diff},
                {
                    "@type": "PropertyValue",
                    "name": "approvalsNotebook",
                    "value": str(_resolve_approvals_notebook_path()),
                },
            ],
        }

    def _html_view(self):
        status_color = "#0f766e" if self.passed else "#b91c1c"
        border_color = "#14b8a6" if self.passed else "#ef4444"
        actual_text = html.escape(json.dumps(self.actual, indent=2, ensure_ascii=True))
        approved_text = html.escape(json.dumps(self.approved, indent=2, ensure_ascii=True))

        if not self.has_approved or self.matches:
            body = f"""
  <details style='margin-top:10px;' open>
    <summary><strong>Value</strong></summary>
    <pre style='white-space:pre-wrap; background:#f8fafc; padding:8px; border-radius:6px;'>{actual_text}</pre>
  </details>
"""
        else:
            body = f"""
  <details style='margin-top:10px;' open>
    <summary><strong>Approved</strong></summary>
    <pre style='white-space:pre-wrap; background:#f8fafc; padding:8px; border-radius:6px;'>{approved_text}</pre>
  </details>
  <details style='margin-top:10px;' open>
    <summary><strong>Actual</strong></summary>
    <pre style='white-space:pre-wrap; background:#f8fafc; padding:8px; border-radius:6px;'>{actual_text}</pre>
  </details>
"""

        return f"""
<div style='border:1px solid {border_color}; border-radius:10px; padding:12px; margin:8px 0; font-family:ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;'>
  <div style='display:flex; justify-content:space-between; align-items:center; gap:8px;'>
    <div>
      <strong>{html.escape(self.test_id)}</strong><br/>
      <span style='font-size:12px; color:#334155;'>{html.escape(self.description)}</span>
    </div>
    <span style='color:{status_color}; font-weight:700;'>{html.escape(self.status)}</span>
  </div>
  <div style='margin-top:8px; font-size:12px; color:#475569;'>
    Approvals notebook: <code>{html.escape(str(_resolve_approvals_notebook_path()))}</code>
  </div>
{body}
</div>
"""

    def _repr_mimebundle_(self, include=None, exclude=None):
        payload = self._jsonld_payload()
        data = {
            "application/ld+json": payload,
            "application/json": payload,
            "text/html": self._html_view(),
            "text/plain": json.dumps(payload, indent=2, ensure_ascii=True),
        }
        metadata = {
            "application/json": {"expanded": True},
            "application/ld+json": {
                "expanded": True,
                "approvalTest": {
                    "testId": self.test_id,
                    "status": self.status,
                    "decision": self.decision,
                    "approved": self.approved,
                },
            },
        }
        return data, metadata


def approval_action(action, test_id):
    if action not in {"approve", "disapprove", "clear"}:
        raise ValueError("action must be approve, disapprove, or clear")
    if test_id not in _APPROVAL_LAST_ACTUAL:
        raise KeyError("No actual value registered for test")

    existing = _APPROVAL_RECORDS.get(test_id, {"test_id": test_id, "approved": None, "decision": None})
    if action == "approve":
        record = {
            "test_id": test_id,
            "approved": _APPROVAL_LAST_ACTUAL[test_id],
            "decision": "Approved",
        }
    elif action == "disapprove":
        record = {
            "test_id": test_id,
            "approved": existing.get("approved"),
            "decision": "Disapproved",
        }
    else:
        record = {
            "test_id": test_id,
            "approved": existing.get("approved"),
            "decision": None,
        }

    save_approval_record(test_id, record)
    _APPROVAL_RECORDS[test_id] = record


def _make_decision_toggle(result):
    approve_btn = widgets.ToggleButton(
        value=result.decision == "Approved",
        description="Approve",
        button_style="success",
        icon="check",
        layout=widgets.Layout(width="190px", height="42px"),
    )
    disapprove_btn = widgets.ToggleButton(
        value=result.decision == "Disapproved",
        description="Disapprove",
        button_style="danger",
        icon="times",
        layout=widgets.Layout(width="190px", height="42px"),
    )
    status = widgets.HTML(
        value=(
            "<small>State: <b>Approved</b></small>"
            if approve_btn.value
            else "<small>State: <b>Disapproved</b></small>"
            if disapprove_btn.value
            else "<small>State: <b>None</b></small>"
        )
    )

    _busy = {"flag": False}

    def _set_status():
        if approve_btn.value:
            status.value = "<small>State: <b>Approved</b> (saved)</small>"
        elif disapprove_btn.value:
            status.value = "<small>State: <b>Disapproved</b> (saved)</small>"
        else:
            status.value = "<small>State: <b>None</b> (saved)</small>"

    def _apply(which):
        if _busy["flag"]:
            return
        _busy["flag"] = True
        try:
            if which == "approve":
                if approve_btn.value:
                    disapprove_btn.value = False
                    approval_action("approve", result.test_id)
                else:
                    approval_action("clear", result.test_id)
            else:
                if disapprove_btn.value:
                    approve_btn.value = False
                    approval_action("disapprove", result.test_id)
                else:
                    approval_action("clear", result.test_id)
            _set_status()
        finally:
            _busy["flag"] = False

    approve_btn.observe(lambda c: _apply("approve") if c["name"] == "value" else None, names="value")
    disapprove_btn.observe(lambda c: _apply("disapprove") if c["name"] == "value" else None, names="value")

    return widgets.VBox([widgets.HBox([approve_btn, disapprove_btn]), status])


def run_approval_test(test_id, description, actual, sort_by=None):
    global _APPROVAL_RECORDS
    _APPROVAL_RECORDS = load_approval_records()
    actual_sorted = stable_records(actual, sort_by) if isinstance(actual, list) else actual
    _APPROVAL_LAST_ACTUAL[test_id] = actual_sorted
    record = _APPROVAL_RECORDS.get(test_id, {})
    return ApprovalTest(
        test_id=test_id,
        description=description,
        actual=actual_sorted,
        approved=record.get("approved"),
        decision=record.get("decision"),
    )


def show_approval_test(test_id, description, actual, sort_by=None):
    result = run_approval_test(test_id, description, actual, sort_by=sort_by)
    display(result)
    display(_make_decision_toggle(result))
    return None


def approval_from_dataframe(test_id, description, actual_df, sort_by=None):
    actual_records = to_iso_records(actual_df)
    return show_approval_test(test_id, description, actual_records, sort_by=sort_by)
