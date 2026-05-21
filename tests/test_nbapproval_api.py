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
