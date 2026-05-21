import pandas as pd
import pytest

import approval_tests
from approval_tests import ApprovalTest
from nbapproval import approval_test


def test_resolve_call_supports_aliases_and_positional_actual():
    test_id, description, actual, sort_by = approval_test._resolve_call(
        (),
        {
            "id": "sample_id",
            "desc": "sample description",
            "actual": {"value": 1},
            "sort_by": ["value"],
        },
    )

    assert test_id == "sample_id"
    assert description == "sample description"
    assert actual == {"value": 1}
    assert sort_by == ["value"]


def test_resolve_call_derives_test_id_from_description_when_missing():
    test_id, description, actual, _ = approval_test._resolve_call(
        ("Known holiday checkpoints match expected names for specific dates.", {"ok": True}),
        {},
    )

    assert test_id == "known_holiday_checkpoints_match_expected_names_for_specific_dates"
    assert description == "Known holiday checkpoints match expected names for specific dates."
    assert actual == {"ok": True}


def test_resolve_call_auto_converts_dataframe_actual():
    frame = pd.DataFrame([{"Date": pd.Timestamp("2024-01-01"), "Expected": "New Year's Day"}])

    _, _, actual, _ = approval_test._resolve_call(
        (),
        {
            "description": "DataFrame case",
            "actual": frame,
        },
    )

    assert isinstance(actual, list)
    assert actual == [{"Date": "2024-01-01", "Expected": "New Year's Day"}]


def test_approval_requires_explicit_approved_decision_even_when_values_match():
    pending = ApprovalTest("t1", "desc", actual={"x": 1}, approved={"x": 1}, decision=None)
    approved = ApprovalTest("t2", "desc", actual={"x": 1}, approved={"x": 1}, decision="Approved")

    assert pending.status == "Pending"
    assert pending.passed is False
    assert approved.status == "Approved"
    assert approved.passed is True


def test_repr_mimebundle_defaults_to_html_and_plaintext_only():
    approval_test.configure(include_json_mime=False)
    result = ApprovalTest("t1", "desc", actual={"x": 1}, approved=None, decision=None)
    data, metadata = result._repr_mimebundle_()

    assert "text/html" in data
    assert "text/plain" in data
    assert "application/json" not in data
    assert "application/ld+json" not in data
    assert metadata == {}


def test_repr_mimebundle_can_opt_in_json_outputs():
    approval_test.configure(include_json_mime=True)
    result = ApprovalTest("t2", "desc", actual={"x": 1}, approved={"x": 1}, decision="Approved")
    data, metadata = result._repr_mimebundle_()

    assert "application/json" in data
    assert "application/ld+json" in data
    assert "application/json" in metadata
    assert "application/ld+json" in metadata

    # Reset to package default for other tests and notebook runs.
    approval_test.configure(include_json_mime=False)


def test_assert_all_approved_fails_when_pending(monkeypatch):
    pending = ApprovalTest("t1", "desc", actual={"x": 1}, approved={"x": 1}, decision=None)
    monkeypatch.setattr(approval_tests, "_RUN_RESULTS", {"t1": pending})

    with pytest.raises(AssertionError, match="Unapproved approval tests found"):
        approval_test.assert_all_approved()


def test_html_view_does_not_repeat_approvals_path_on_each_card():
    result = ApprovalTest("t1", "desc", actual={"x": 1}, approved=None, decision=None)
    html = result._html_view()
    assert "Approvals notebook:" not in html


def test_status_report_includes_counts_and_path(monkeypatch):
    approved = ApprovalTest("t1", "desc", actual={"x": 1}, approved={"x": 1}, decision="Approved")
    pending = ApprovalTest("t2", "desc", actual={"x": 2}, approved={"x": 2}, decision=None)
    monkeypatch.setattr(approval_tests, "_RUN_RESULTS", {"t1": approved, "t2": pending})

    report = approval_test.status_report()
    assert report["total"] == 2
    assert report["approved"] == 1
    assert report["pending"] == 1
    assert report["all_approved"] is False
    assert report["tests"]["t1"] == "Approved"
    assert report["tests"]["t2"] == "Pending"
    assert isinstance(report["approvals_notebook_path"], str)
    assert report["approvals_notebook_path"].endswith(".ipynb")


def test_facade_exposes_approvals_notebook_path_property():
    path = approval_test.approvals_notebook_path
    assert isinstance(path, str)
    assert path.endswith(".ipynb")


def test_parse_approve_magic_header_supports_options_and_description():
    test_id, description, sort_by_expr = approval_tests._parse_approve_magic_header(
        '--id my_test --sort-by "[\'Date\', \'Expected\']" free form description'
    )

    assert test_id == "my_test"
    assert description == "free form description"
    assert sort_by_expr == "['Date', 'Expected']"


def test_run_approve_magic_evaluates_expression_and_calls_facade(monkeypatch):
    captured = {}

    class FakeApprovalTest:
        def __call__(self, *args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return "ok"

    monkeypatch.setattr(approval_tests, "approval_test", FakeApprovalTest())

    result = approval_tests._run_approve_magic(
        "actual_df",
        description="Magic description",
        test_id="magic_test",
        sort_by_expr="['Date']",
        user_ns={"actual_df": [{"Date": "2024-01-01"}]},
    )

    assert result == "ok"
    assert captured["kwargs"]["id"] == "magic_test"
    assert captured["kwargs"]["description"] == "Magic description"
    assert captured["kwargs"]["actual"] == [{"Date": "2024-01-01"}]
    assert captured["kwargs"]["sort_by"] == ["Date"]


def test_run_approve_magic_executes_block_and_uses_last_expression(monkeypatch):
    captured = {}

    class FakeApprovalTest:
        def __call__(self, *args, **kwargs):
            captured["kwargs"] = kwargs
            return "ok"

    monkeypatch.setattr(approval_tests, "approval_test", FakeApprovalTest())

    result = approval_tests._run_approve_magic(
        "x = 1\ny = x + 2\ny",
        description="block case",
        user_ns={},
    )

    assert result == "ok"
    assert captured["kwargs"]["actual"] == 3
    assert captured["kwargs"]["description"] == "block case"


def test_handle_approve_magic_line_expression(monkeypatch):
    captured = {}

    def fake_run(expression, *, description=None, test_id=None, sort_by_expr=None, user_ns=None):
        captured["expression"] = expression
        captured["description"] = description
        captured["test_id"] = test_id
        captured["sort_by_expr"] = sort_by_expr
        captured["user_ns"] = user_ns
        return "ok"

    monkeypatch.setattr(approval_tests, "_run_approve_magic", fake_run)
    result = approval_tests._handle_approve_magic(
        'bool(df["Date"].is_monotonic_increasing)',
        user_ns={"df": "stub"},
    )

    assert result == "ok"
    assert captured["expression"] == 'bool(df["Date"].is_monotonic_increasing)'
    assert captured["description"] is None
    assert captured["test_id"] is None
    assert captured["sort_by_expr"] is None


def test_handle_approve_magic_cell_expression(monkeypatch):
    captured = {}

    def fake_run(expression, *, description=None, test_id=None, sort_by_expr=None, user_ns=None):
        captured["expression"] = expression
        captured["description"] = description
        captured["test_id"] = test_id
        captured["sort_by_expr"] = sort_by_expr
        captured["user_ns"] = user_ns
        return "ok"

    monkeypatch.setattr(approval_tests, "_run_approve_magic", fake_run)
    result = approval_tests._handle_approve_magic(
        '--id holidays_2026 --sort-by "[\'Date\']" Federal holidays for 2026',
        cell='df.loc[df["Year"] == 2026, ["Date", "Holiday"]]',
        user_ns={"df": "stub"},
    )

    assert result == "ok"
    assert captured["expression"] == 'df.loc[df["Year"] == 2026, ["Date", "Holiday"]]'
    assert captured["description"] == "Federal holidays for 2026"
    assert captured["test_id"] == "holidays_2026"
    assert captured["sort_by_expr"] == "['Date']"
