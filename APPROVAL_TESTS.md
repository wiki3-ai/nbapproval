# Approval Tests Utility Guide

This document explains how the approval testing utility works, how it initializes, how it resolves paths, and how to use it in notebooks.

## Overview

The utility lives in:

- `approval_tests.py`

Typical notebook usage is a single import:

```python
from nbapproval import approval_test
```

Then call:

- `approval_test(...)` for dict/list/DataFrame payloads
- `approval_test.from_dataframe(...)` as optional convenience
- `approval_test.to_iso_records(df)` to normalize datetime columns into stable JSON-ready records

## Runtime Initialization Logic

The utility initializes lazily at call time, not at import time.

When you call `approval_test(...)`:

1. `run_approval_test(...)` is called.
2. It loads approval records from the approvals notebook.
3. It stores current actual value for the current `test_id` in in-memory state (`_APPROVAL_LAST_ACTUAL`).
4. It computes result state (`Approved`, `Disapproved`, `changed`, or `missing-approved`).
5. It renders:
   - rich value/status panel (`ApprovalTest` rich repr), and
   - button controls (`Approve`, `Disapprove`, `Reset`).

No extra bootstrap cell is required for normal use.

## How We Get the Notebook Path

Path resolution has this order:

1. Explicit configuration via API:
   - `approval_test.configure(test_notebook_path=..., approvals_notebook_path=...)`
2. Auto-detection from runtime hints (best effort):
   - env keys like `VSCODE_NOTEBOOK_PATH`, `VSCODE_CWD_NOTEBOOK_PATH`, `JPY_SESSION_NAME`
   - IPython namespace keys like `__vsc_ipynb_file__`, `__notebook_file__`, `NOTEBOOK_PATH`
3. If current notebook path is known, approvals path is computed strictly as:
   - `<dir of notebook>/__approvals__/<name of notebook>`
4. If notebook path is unknown, fallback behavior is used:
   - check `./__approvals__/*.ipynb`
   - if one file exists, use it
   - if multiple files exist, prefer `*_tested.ipynb`, then non-generic file names
   - else default to `./__approvals__/approvals.ipynb`

Important note:

- The intended canonical rule is always:
   - `<dir of current notebook>/__approvals__/<name of current notebook>`
- Fallback selection is only used when runtime path detection cannot determine the current notebook path.

## Approved Values Notebook Format

Approvals are stored in a Jupyter notebook file as raw cells.

- One raw cell per `test_id`
- Raw cell metadata includes:
  - `approval_test_id`
  - timestamps (`created_at`, optional `updated_at`)
- Raw cell source JSON record includes:
  - `test_id`
  - `approved`
  - `decision` (None, `Approved`, or `Disapproved`)

Example record body:

```json
{
  "test_id": "year_boundaries",
  "approved": {
    "startYear": 2024,
    "endYear": 2028
  },
  "decision": "Approved"
}
```

`test_id` is the identity key. Keep it stable and unique for each logical approval test.

Recommended pattern for larger notebooks:

- use namespace-like IDs such as `holiday.required_columns` or `holiday.2026.independence_observed`
- avoid renaming `test_id` unless you intentionally want a new approval history

## Decision and Display State Rules

Decision values are normalized to:

- `None`
- `Approved`
- `Disapproved`

Rendering rules:

1. No approved value:
   - Status: `missing-approved`
   - Show one `Value` block (actual)
2. Approved exists and equals actual but decision is not explicitly approved:
   - Status: `Pending`
   - Show one `Value` block
3. Approved exists and equals actual and decision is explicitly approved:
   - Status: `Approved`
   - Show one `Value` block
4. Approved exists and does not equal actual:
   - Status: `changed`
   - Show `Approved` and `Actual` blocks
5. If decision is `Approved` but values no longer match:
   - effective decision is treated as `None` for display
   - prevents stale "Approved" UI state on mismatch

## Buttons Behavior

Buttons are mutually exclusive toggles:

- `Approve`
- `Disapprove`
- `Reset`

Behavior:

- Selecting `Approve` writes current actual as approved and sets decision `Approved`
- Selecting `Disapprove` preserves approved value and sets decision `Disapproved`
- `Reset` clears decision to `None` (approved value retained)
- Selected button changes label (`Approve` -> `Approved`, `Disapprove` -> `Disapproved`) with stronger style and border

## API Reference

Imported symbol:

```python
from nbapproval import approval_test
```

Methods:

- `approval_test(description, actual, sort_by=None)`
- `approval_test(test_id=..., description=..., actual=..., sort_by=None)`
- `approval_test(id=..., desc=..., actual=..., sort_by=None)`
- `approval_test.from_dataframe(...)` (optional convenience)
- `approval_test.to_iso_records(frame)`
- `approval_test.configure(test_notebook_path=None, approvals_notebook_path=None, include_json_mime=None)`
- `approval_test.assert_all_approved(require_any=True)`

Terse API notes:

- if `test_id`/`id` is omitted, id is derived from description text
- if the first positional argument is a string, it is treated as description
- if DataFrame is passed as `actual`, it is automatically converted using ISO-safe records

## Recommended Notebook Pattern

```python
from nbapproval import approval_test

approval_test(
   "Dataframe includes required columns.",
   {"columns": sorted(df.columns.tolist())},
)
```

For DataFrames:

```python
approval_test(
   "Federal holidays for 2026 (including observed).",
   df.loc[df["Year"] == 2026, ["Date", "Holiday"]],
    sort_by=["Date", "Holiday"],
)
```

For CI/non-interactive runs (Papermill), add a final guard cell:

```python
approval_test.assert_all_approved()
```

This raises an `AssertionError` if any approval test status is not `Approved`.

## Papermill Usage

Execute the notebook:

```bash
papermill /workspaces/coding/holiday_calculator_tested.ipynb /workspaces/coding/holiday_calculator_tested.papermill.ipynb
```

Output file naming note:

- the output suffix is not required to be `.papermill`
- any output notebook filename works
- when current notebook path is detectable, approvals follow the canonical per-notebook rule
- when not detectable, fallback selection may be used; in CI, set `approval_test.configure(...)` for deterministic behavior

Behavior with guard cell:

- all approved: papermill exits `0`
- any `missing-approved`, `changed`, or `Disapproved`: papermill fails with assertion error

## Troubleshooting

### Approved values not found

1. Check rendered "Approvals notebook" path in output.
2. Confirm that file exists.
3. If needed, pin explicit path once:

```python
from nbapproval import approval_test
approval_test.configure(
    test_notebook_path="/absolute/path/to/your_notebook.ipynb",
    approvals_notebook_path=None,
)
```

### Wrong approvals notebook selected after renaming/moving notebooks

Use explicit `approval_test.configure(...)` in one setup cell so the path is deterministic.

### Multiple notebooks sharing one approvals file

This is supported only if all `test_id` values are unique across those notebooks.

### Stale behavior after utility edits

Restart notebook kernel or reload module by re-running the import cell in a fresh kernel session.
