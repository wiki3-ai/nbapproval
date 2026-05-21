# nbapproval

Notebook-friendly approval testing for Python and Jupyter.

`nbapproval` lets you compare actual notebook outputs to approved values,
store approvals in a separate approvals notebook, and fail CI runs when
approvals are missing or mismatched.

## Install

```bash
pip install nbapproval
```

## Quick Start

```python
from nbapproval import approval_test

approval_test(
    "Simple approval check",
    {"value": 42},
)

approval_test.assert_all_approved()
```

## API (Terse-First)

Primary call supports concise notebook usage:

```python
approval_test(description, actual, sort_by=None)
```

Also supported:

- `id` alias for `test_id`
- `desc` alias for `description`
- keyword form: `actual=...`
- automatic `test_id` derivation from `description` when omitted
- pandas DataFrame values as `actual` (auto-converted to stable records)

Examples:

```python
# Explicit id + keyword style
approval_test(
    id="known_holiday_checkpoints_match_expected_names_for_specific_dates",
    desc="Known holiday checkpoints match expected names for specific dates.",
    actual=approval_test.to_iso_records(actual_df),
    sort_by=["Date", "Expected"],
)

# Terse positional style (id auto-derived from description)
approval_test(
    "Known holiday checkpoints match expected names for specific dates.",
    actual_df,
    sort_by=["Date", "Expected"],
)
```

`approval_test.from_dataframe(...)` remains available, but is optional now because
the main call handles DataFrames directly.

## Testing

Run tests with:

```bash
pip install -e .[dev]
pytest -q
```

## Notes

- Stable and unique `test_id` values are required.
- For deterministic CI runs, configure an explicit approvals notebook path.
- Works well with Papermill-driven notebook execution.

## License

Apache License 2.0. See [LICENSE](LICENSE).
