"""Paid refusals keep their cause without buying the same request again."""

import json
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from temporalio.exceptions import ApplicationError
from test_ai_answers_activity import FakeRunDatabase
from test_organic_audit import activities_fixture
from test_paid_ads_monitor_activities import fixture as monitor_fixture
from test_payment_recovery import setup as payment_fixture

from tin_lite.ai_answers_activities import ReceiptLedger
from tin_lite.billing_contracts import BillingError
from tin_lite.organic_audit_ai import AuditValidationError


@pytest.mark.parametrize("workflow", ["audit", "monitor", "ai_answers"])
@pytest.mark.parametrize(
    "code",
    [
        "spending_limit",
        "run_limit",
        "project_limit",
        "unpriced_model",
        "unmetered_operation",
        "operation_already_attempted",
        "usage_pending",
        "insufficient_funds",
        "spending_stopped",
    ],
)
async def test_refusal_classification_and_replay(workflow, code):
    call = AsyncMock(side_effect=BillingError(code, "Private diagnostic must not escape"))
    if workflow == "audit":
        work, db, *_ = await activities_fixture()

        async def invoke():
            return await work._paid(str(db.run.id), "answer:test", {}, "0.01", call)
    elif workflow == "monitor":
        work, db, *_ = monitor_fixture()
        await work.prepare(str(db.run.id))

        async def invoke():
            return await work._paid(str(db.run.id), "model:test", {}, "0.01", call, needs="model")
    else:
        db = FakeRunDatabase()
        work = ReceiptLedger(db, run_id=db.run.id, stage="test")

        async def invoke():
            return await work.once("request", reserve_usd=Decimal("0.01"), call=call)

    result = await invoke()
    assert await invoke() == result
    assert call.await_count == 1
    is_limit = code in {"spending_limit", "run_limit", "project_limit"}
    assert result["reason"] == ("spending_limit" if is_limit else "billing_refused")
    if not is_limit:
        assert result["billing_error_code"] == code
    assert "Private diagnostic" not in json.dumps(result)


@pytest.mark.parametrize("code", ["run_limit", "project_limit", "unpriced_model", "usage_pending"])
async def test_monitor_projected_failure_keeps_the_classification(code):
    work, db, *_ = monitor_fixture()
    run_id = str(db.run.id)
    await work.prepare(run_id)
    work.router.generate.side_effect = BillingError(code, "Private diagnostic must not escape")
    for _ in range(2):
        with pytest.raises(ApplicationError):
            await work._model(run_id, "brief", "system", "user", {}, 100, "low")
    assert work.router.generate.await_count == 1
    await work.failure(run_id)
    message = db.project_failure.await_args.kwargs["error_message"]
    assert ("spending limit" in message) is (code in {"run_limit", "project_limit"})
    if code not in {"run_limit", "project_limit"}:
        assert code in message and "could not be confirmed" not in message
    assert "Private diagnostic" not in message


def test_audit_billing_gap_has_an_honest_explanation():
    gap = AuditValidationError("billing_refused")
    assert "billing check refused" in str(gap) and "spending limit" not in str(gap)


@pytest.mark.parametrize("code", ["spending_stopped", "unmetered_operation", "run_limit"])
async def test_required_ads_read_projects_billing_cause_without_retrying(code):
    work, db, _, integrations, _ = monitor_fixture()
    run_id = str(db.run.id)
    await work.prepare(run_id)
    integrations.google_ads_call = AsyncMock(side_effect=BillingError(code, "Private diagnostic"))
    for _ in range(2):
        with pytest.raises(ApplicationError) as caught:
            await work.read(run_id)
        assert caught.value.non_retryable is True
    assert integrations.google_ads_call.await_count == 1
    assert integrations.mutations == []
    assert work.router.generate.await_count == 0
    await work.failure(run_id)
    message = db.project_failure.await_args.kwargs["error_message"]
    assert ("spending limit" in message) is (code == "run_limit")
    if code != "run_limit":
        assert code in message
    assert "Private diagnostic" not in message


@pytest.mark.parametrize(
    "code", ["unpriced_model", "unmetered_operation", "operation_already_attempted"]
)
async def test_payment_drafting_refusal_does_not_claim_a_credit_limit(monkeypatch, code):
    fixture = payment_fixture(monkeypatch)
    fixture.router.generate = AsyncMock(side_effect=BillingError(code, "Private diagnostic"))
    with pytest.raises(ApplicationError) as caught:
        await fixture.activities._model(fixture.run_id, "draft request")
    assert code in str(caught.value) and "spending limits" not in str(caught.value)
    assert "Private diagnostic" not in str(caught.value)
    assert await fixture.activities._model(fixture.run_id, "draft request") is None
    assert fixture.router.generate.await_count == 1
