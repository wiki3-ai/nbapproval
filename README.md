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
    test_id="example.simple",
    description="Simple approval check",
    actual={"value": 42},
)

approval_test.assert_all_approved()
```

## Notes

- Stable and unique `test_id` values are required.
- For deterministic CI runs, configure an explicit approvals notebook path.
- Works well with Papermill-driven notebook execution.

## License

Apache License 2.0. See [LICENSE](LICENSE).
