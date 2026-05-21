# Approval Tests Utility Guide

This document explains how the approval testing utility works, how it initializes, how it resolves paths, and how to use it in notebooks.

## Overview

The utility lives in:

- `approval_tests.py`

Typical notebook usage is a single import:

```python
from approval_tests import approval_test
```

Then call:

- `approval_test(...)` for dict/list payloads
- `approval_test.from_dataframe(...)` for DataFrames
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

## Decision and Display State Rules

Decision values are normalized to:

- `None`
- `Approved`
- `Disapproved`

Rendering rules:

1. No approved value:
   - Status: `missing-approved`
   - Show one `Value` block (actual)
2. Approved exists and equals actual:
   - Status: `Approved` (unless decision is `Disapproved`)
   - Show one `Value` block
3. Approved exists and does not equal actual:
   - Status: `changed`
   - Show `Approved` and `Actual` blocks
4. If decision is `Approved` but values no longer match:
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
from approval_tests import approval_test
```

Methods:

- `approval_test(test_id=..., description=..., actual=..., sort_by=None)`
- `approval_test.from_dataframe(test_id=..., description=..., actual_df=..., sort_by=None)`
- `approval_test.to_iso_records(frame)`
- `approval_test.configure(test_notebook_path=None, approvals_notebook_path=None)`

## Recommended Notebook Pattern

```python
from approval_tests import approval_test

approval_test(
    test_id="required_columns_present",
    description="Dataframe includes required columns.",
    actual={"columns": sorted(df.columns.tolist())},
)
```

For DataFrames:

```python
approval_test.from_dataframe(
    test_id="approval_us_2026_holidays",
    description="Federal holidays for 2026 (including observed).",
    actual_df=df.loc[df["Year"] == 2026, ["Date", "Holiday"]],
    sort_by=["Date", "Holiday"],
)
```

## Troubleshooting

### Approved values not found

1. Check rendered "Approvals notebook" path in output.
2. Confirm that file exists.
3. If needed, pin explicit path once:

```python
from approval_tests import approval_test
approval_test.configure(
    test_notebook_path="/absolute/path/to/your_notebook.ipynb",
    approvals_notebook_path=None,
)
```

### Wrong approvals notebook selected after renaming/moving notebooks

Use explicit `approval_test.configure(...)` in one setup cell so the path is deterministic.

### Stale behavior after utility edits

Restart notebook kernel or reload module by re-running the import cell in a fresh kernel session.
