import json
import html
import re
import os
import shlex
import ast
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import ipywidgets as widgets
from IPython.display import display

_APPROVAL_LAST_ACTUAL = {}
_APPROVAL_RECORDS = {}
_RUN_RESULTS = {}
_TEST_NOTEBOOK_PATH = None
_APPROVALS_NOTEBOOK_PATH = None
_INCLUDE_JSON_MIME = False


def configure_approval_store(
    test_notebook_path=None,
    approvals_notebook_path=None,
    include_json_mime=None,
):
    global _TEST_NOTEBOOK_PATH, _APPROVALS_NOTEBOOK_PATH, _INCLUDE_JSON_MIME
    _TEST_NOTEBOOK_PATH = test_notebook_path
    _APPROVALS_NOTEBOOK_PATH = approvals_notebook_path
    if include_json_mime is not None:
        _INCLUDE_JSON_MIME = bool(include_json_mime)


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


def _derive_test_id_from_description(description):
    token = re.sub(r"[^a-z0-9]+", "_", str(description).strip().lower()).strip("_")
    return token or "approval_test"


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _resolve_tests_notebook_path():
    if _TEST_NOTEBOOK_PATH:
        return Path(_TEST_NOTEBOOK_PATH).resolve()
    detected = _detect_current_notebook_path()
    if detected is not None:
        return detected
    return None


def _detect_current_notebook_path():
    # Best-effort runtime detection across notebook frontends.
    raw_candidates = []
    for key in ("VSCODE_NOTEBOOK_PATH", "VSCODE_CWD_NOTEBOOK_PATH", "JPY_SESSION_NAME"):
        value = os.environ.get(key)
        if value:
            raw_candidates.append(value)

    try:
        from IPython import get_ipython

        ip = get_ipython()
        if ip is not None:
            ns = getattr(ip, "user_ns", {})
            for key in ("__vsc_ipynb_file__", "__notebook_file__", "NOTEBOOK_PATH"):
                value = ns.get(key)
                if value:
                    raw_candidates.append(str(value))
    except Exception:
        pass

    for candidate in raw_candidates:
        if not str(candidate).endswith(".ipynb"):
            continue
        path = Path(candidate)
        if not path.is_absolute():
            path = Path.cwd() / path
        if path.exists():
            return path.resolve()
    return None


def _resolve_approvals_notebook_path():
    if _APPROVALS_NOTEBOOK_PATH:
        return Path(_APPROVALS_NOTEBOOK_PATH).resolve()

    tests_nb = _resolve_tests_notebook_path()
    if tests_nb is not None:
        return tests_nb.parent / "__approvals__" / tests_nb.name

    approvals_dir = Path.cwd() / "__approvals__"
    candidates = sorted(approvals_dir.glob("*.ipynb")) if approvals_dir.exists() else []
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        tested = [p for p in candidates if p.name.endswith("_tested.ipynb")]
        if tested:
            return tested[0]
        non_generic = [p for p in candidates if p.name != "approvals.ipynb"]
        if non_generic:
            return non_generic[0]
    return approvals_dir / "approvals.ipynb"


def get_approvals_notebook_path():
    return str(_resolve_approvals_notebook_path())


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
        return {
            "test_id": parsed_value.get("test_id") or test_id,
            "approved": parsed_value.get("approved"),
            "decision": _normalize_decision(parsed_value.get("decision")),
        }
    return {
        "test_id": test_id,
        "approved": parsed_value,
        "decision": "Approved" if parsed_value is not None else None,
    }


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
        self.raw_decision = decision
        self.decision = decision

        self.has_approved = approved is not None
        self.matches = self.has_approved and approved == actual

        if self.decision == "Approved" and not self.matches:
            self.decision = None

        # A test is only fully approved when the reviewer explicitly approved
        # and the approved value still matches the current actual value.
        if self.decision == "Disapproved":
            self.passed = False
            self.status = "Disapproved"
        elif not self.has_approved:
            self.passed = False
            self.status = "missing-approved"
        elif self.decision == "Approved" and self.matches:
            self.passed = True
            self.status = "Approved"
        elif self.matches:
            self.passed = False
            self.status = "Pending"
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
{body}
</div>
"""

    def _repr_mimebundle_(self, include=None, exclude=None):
        payload = self._jsonld_payload()
        data = {
            "text/html": self._html_view(),
            "text/plain": json.dumps(payload, indent=2, ensure_ascii=True),
        }
        metadata = {}

        if _INCLUDE_JSON_MIME:
            data["application/ld+json"] = payload
            data["application/json"] = payload
            metadata["application/json"] = {"expanded": True}
            metadata["application/ld+json"] = {
                "expanded": True,
                "approvalTest": {
                    "testId": self.test_id,
                    "status": self.status,
                    "decision": self.decision,
                    "approved": self.approved,
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
        value=result.decision == "Approved" and result.matches,
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
    reset_btn = widgets.Button(
        description="Reset",
        button_style="warning",
        icon="undo",
        layout=widgets.Layout(width="120px", height="42px"),
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

    def _style_buttons():
        approve_btn.description = "Approved" if approve_btn.value else "Approve"
        disapprove_btn.description = "Disapproved" if disapprove_btn.value else "Disapprove"

        approve_btn.style.button_color = "#0f766e" if approve_btn.value else ""
        disapprove_btn.style.button_color = "#991b1b" if disapprove_btn.value else ""

        approve_btn.layout.border = "3px solid #0d9488" if approve_btn.value else "2px solid #9ca3af"
        disapprove_btn.layout.border = "3px solid #dc2626" if disapprove_btn.value else "2px solid #9ca3af"

        reset_btn.disabled = not (approve_btn.value or disapprove_btn.value)

    def _set_status():
        if approve_btn.value:
            status.value = "<small>State: <b>Approved</b> (saved)</small>"
        elif disapprove_btn.value:
            status.value = "<small>State: <b>Disapproved</b> (saved)</small>"
        else:
            status.value = "<small>State: <b>None</b> (saved)</small>"
        _style_buttons()

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

    def _reset(_):
        if _busy["flag"]:
            return
        _busy["flag"] = True
        try:
            approve_btn.value = False
            disapprove_btn.value = False
            approval_action("clear", result.test_id)
            _set_status()
        finally:
            _busy["flag"] = False

    reset_btn.on_click(_reset)
    _style_buttons()

    return widgets.VBox([widgets.HBox([approve_btn, disapprove_btn, reset_btn]), status])


def run_approval_test(test_id, description, actual, sort_by=None):
    global _APPROVAL_RECORDS, _RUN_RESULTS
    _APPROVAL_RECORDS = load_approval_records()
    actual_sorted = stable_records(actual, sort_by) if isinstance(actual, list) else actual
    _APPROVAL_LAST_ACTUAL[test_id] = actual_sorted
    record = _APPROVAL_RECORDS.get(test_id, {})
    result = ApprovalTest(
        test_id=test_id,
        description=description,
        actual=actual_sorted,
        approved=record.get("approved"),
        decision=record.get("decision"),
    )
    _RUN_RESULTS[test_id] = result
    return result


def show_approval_test(test_id, description, actual, sort_by=None):
    result = run_approval_test(test_id, description, actual, sort_by=sort_by)
    display(result)
    display(_make_decision_toggle(result))
    return None


def approval_from_dataframe(test_id, description, actual_df, sort_by=None):
    actual_records = to_iso_records(actual_df)
    return show_approval_test(test_id, description, actual_records, sort_by=sort_by)


def assert_all_approved(require_any=True):
    report = approval_status_report()

    if require_any and not _RUN_RESULTS:
        raise AssertionError(
            "No approval tests ran in this session.\n"
            f"Approvals notebook: {report['approvals_notebook_path']}"
        )

    print(
        "Approval summary: "
        f"{report['approved']}/{report['total']} Approved"
        f" (Pending={report['pending']}, changed={report['changed']}, "
        f"Disapproved={report['disapproved']}, missing-approved={report['missing_approved']})"
    )
    print(f"Approvals notebook: {report['approvals_notebook_path']}")

    failing = [
        f"{test_id}: {result.status}"
        for test_id, result in sorted(_RUN_RESULTS.items())
        if result.status != "Approved"
    ]
    if failing:
        details = "\n".join(failing)
        raise AssertionError(
            "Unapproved approval tests found:\n"
            + details
            + "\n"
            + f"Approvals notebook: {report['approvals_notebook_path']}"
        )


def approval_status_report():
    path = get_approvals_notebook_path()
    counts = {
        "Approved": 0,
        "Pending": 0,
        "changed": 0,
        "Disapproved": 0,
        "missing-approved": 0,
    }

    tests = {}
    for test_id, result in sorted(_RUN_RESULTS.items()):
        status = result.status
        if status not in counts:
            counts[status] = 0
        counts[status] += 1
        tests[test_id] = status

    total = sum(counts.values())
    failing = [test_id for test_id, status in tests.items() if status != "Approved"]

    return {
        "approvals_notebook_path": path,
        "total": total,
        "approved": counts.get("Approved", 0),
        "pending": counts.get("Pending", 0),
        "changed": counts.get("changed", 0),
        "disapproved": counts.get("Disapproved", 0),
        "missing_approved": counts.get("missing-approved", 0),
        "all_approved": total > 0 and not failing,
        "tests": tests,
    }


def _parse_approve_magic_header(header):
    tokens = shlex.split(header) if header else []
    test_id = None
    description_parts = []
    sort_by_expr = None

    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in {"--id", "-i"}:
            if i + 1 >= len(tokens):
                raise ValueError("--id requires a value")
            test_id = tokens[i + 1]
            i += 2
            continue
        if token in {"--desc", "--description", "-d"}:
            if i + 1 >= len(tokens):
                raise ValueError("--desc/--description requires a value")
            description_parts.append(tokens[i + 1])
            i += 2
            continue
        if token in {"--sort-by", "-s"}:
            if i + 1 >= len(tokens):
                raise ValueError("--sort-by requires a Python expression value")
            sort_by_expr = tokens[i + 1]
            i += 2
            continue

        description_parts.append(token)
        i += 1

    description = " ".join(description_parts).strip() or None
    return test_id, description, sort_by_expr


def _run_approve_magic(expression, *, description=None, test_id=None, sort_by_expr=None, user_ns=None):
    namespace = user_ns or {}
    actual = _evaluate_magic_source(expression, namespace)
    sort_by = eval(sort_by_expr, namespace) if sort_by_expr else None

    effective_description = description or expression.strip()
    return approval_test(
        id=test_id,
        description=effective_description,
        actual=actual,
        sort_by=sort_by,
    )


def _evaluate_magic_source(source, namespace):
    source = (source or "").strip()
    if not source:
        raise ValueError("approve magic requires Python code")

    module = ast.parse(source, mode="exec")
    if not module.body:
        raise ValueError("approve magic requires Python code")

    # Execute all statements and treat the final expression (if present)
    # as the value to be approved.
    if isinstance(module.body[-1], ast.Expr):
        prefix = ast.Module(body=module.body[:-1], type_ignores=[])
        if prefix.body:
            exec(compile(prefix, "<approve-magic>", "exec"), namespace)
        expr = ast.Expression(module.body[-1].value)
        return eval(compile(expr, "<approve-magic>", "eval"), namespace)

    exec(compile(module, "<approve-magic>", "exec"), namespace)
    return namespace.get("_", None)


def _handle_approve_magic(line, cell=None, *, user_ns=None):
    raw = (line or "").strip()
    expression = (cell or "").strip() if cell is not None else None

    if cell is None:
        # Line form:
        # %approve <python-expression>
        # %approve [--id value] [--desc "text"] [--sort-by "['col']"] :: <python-expression>
        if not raw:
            raise ValueError("%approve requires an expression")

        if "::" in raw:
            header, expression = raw.split("::", 1)
            test_id, description, sort_by_expr = _parse_approve_magic_header(header.strip())
            return _run_approve_magic(
                expression.strip(),
                description=description,
                test_id=test_id,
                sort_by_expr=sort_by_expr,
                user_ns=user_ns,
            )

        return _run_approve_magic(raw, user_ns=user_ns)

    # Cell form:
    # %%approve [--id value] [--desc "text"] [--sort-by "['col']"] [freeform description]
    # <python-expression>
    test_id, description, sort_by_expr = _parse_approve_magic_header(raw)
    if not expression:
        raise ValueError("%%approve requires a Python expression in the cell body")
    return _run_approve_magic(
        expression,
        description=description,
        test_id=test_id,
        sort_by_expr=sort_by_expr,
        user_ns=user_ns,
    )


def _register_ipython_magics(ip):
    from IPython.core.magic import Magics, line_cell_magic, magics_class

    @magics_class
    class ApprovalMagics(Magics):
        @line_cell_magic
        def approve(self, line, cell=None):
            return _handle_approve_magic(line, cell=cell, user_ns=self.shell.user_ns)

    ip.register_magics(ApprovalMagics)


def load_ipython_extension(ipython):
    _register_ipython_magics(ipython)


def _try_auto_register_magics():
    try:
        from IPython import get_ipython

        ip = get_ipython()
        if ip is not None:
            _register_ipython_magics(ip)
    except Exception:
        pass


class _ApprovalTestFacade:
    _MISSING = object()

    def _resolve_call(self, args, kwargs):
        params = dict(kwargs)

        test_id = params.pop("test_id", None)
        id_alias = params.pop("id", None)
        description = params.pop("description", None)
        desc_alias = params.pop("desc", None)
        actual = params.pop("actual", self._MISSING)
        sort_by = params.pop("sort_by", None)

        if test_id is not None and id_alias is not None and test_id != id_alias:
            raise ValueError("test_id and id were both provided with different values")
        if description is not None and desc_alias is not None and description != desc_alias:
            raise ValueError("description and desc were both provided with different values")

        if test_id is None:
            test_id = id_alias
        if description is None:
            description = desc_alias

        remaining_args = list(args)
        if remaining_args and description is None and isinstance(remaining_args[0], str):
            description = remaining_args.pop(0)

        if remaining_args and actual is self._MISSING:
            actual = remaining_args.pop(0)

        if remaining_args:
            raise TypeError("Too many positional arguments")
        if params:
            unknown = ", ".join(sorted(params.keys()))
            raise TypeError(f"Unexpected keyword arguments: {unknown}")

        if test_id is None:
            if description is None:
                raise TypeError("Either test_id/id or description/desc must be provided")
            test_id = _derive_test_id_from_description(description)

        if description is None:
            description = str(test_id)

        if actual is self._MISSING:
            raise TypeError("Missing required argument: actual")

        # DataFrames are converted automatically, so a separate from_dataframe call
        # is optional for the common case.
        if isinstance(actual, pd.DataFrame):
            actual = to_iso_records(actual)

        return test_id, description, actual, sort_by

    def __call__(self, *args, **kwargs):
        test_id, description, actual, sort_by = self._resolve_call(args, kwargs)
        return show_approval_test(
            test_id=test_id,
            description=description,
            actual=actual,
            sort_by=sort_by,
        )

    def from_dataframe(self, *args, **kwargs):
        params = dict(kwargs)
        if "actual_df" in params and "actual" not in params:
            params["actual"] = params.pop("actual_df")
        return self.__call__(
            *args,
            **params,
        )

    def to_iso_records(self, frame):
        return to_iso_records(frame)

    def configure(
        self,
        *,
        test_notebook_path=None,
        approvals_notebook_path=None,
        include_json_mime=None,
    ):
        return configure_approval_store(
            test_notebook_path=test_notebook_path,
            approvals_notebook_path=approvals_notebook_path,
            include_json_mime=include_json_mime,
        )

    def assert_all_approved(self, require_any=True):
        return assert_all_approved(require_any=require_any)

    def status_report(self):
        return approval_status_report()

    @property
    def approvals_notebook_path(self):
        return get_approvals_notebook_path()


approval_test = _ApprovalTestFacade()

_try_auto_register_magics()
