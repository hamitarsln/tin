import pytest
from temporalio.exceptions import ApplicationError
from test_paid_ads_launch import account, assessment, inputs, site
from test_paid_ads_launch_activities import fixture as launch_fixture
from test_paid_ads_monitor_activities import fixture as monitor_fixture

from tin_lite import paid_ads_launch


@pytest.mark.parametrize("currency", ["EUR", "GBP", "TRY", None])
def test_launch_does_not_treat_account_currency_as_dollars(currency):
    acct = account()
    acct["customer"]["currency_code"] = currency
    gate = paid_ads_launch.gate(
        assessment=assessment(), account=acct, site=site(), inputs=inputs(), existing_campaign=None
    )
    assert gate["outcome"] == "unsupported_currency"
    assert gate["outcome"] in paid_ads_launch.OUTCOMES
    assert "USD" in gate["text"]


@pytest.mark.parametrize("currency", ["EUR", None])
async def test_launch_stops_before_model_or_tracking_write(currency):
    activities, db, storage, script, router, integrations, model = await launch_fixture()
    original = script.rows

    def rows(query):
        result = original(query)
        if "FROM customer" in query:
            result[0]["customer"]["currencyCode"] = currency
        return result

    script.rows = rows
    run_id = str(db.run.id)
    await activities.prepare(run_id)
    await activities.gather(run_id)
    assert await activities.draft(run_id) == "setup"
    assert not router.generate.await_count
    assert all(kind == "search" for kind, _, _ in script.calls)


@pytest.mark.parametrize("currency", ["EUR", "GBP", "TRY", None])
async def test_monitor_stops_before_model_or_mutation(currency):
    activities, db, storage, integrations, model = monitor_fixture()
    original = integrations.google_ads_call

    async def call(**kwargs):
        if kwargs["kind"] == "search" and "FROM customer" in kwargs["request"]["query"]:
            return {"rows": [{"customer": {"id": integrations.customer, "currencyCode": currency}}]}
        return await original(**kwargs)

    integrations.google_ads_call = call
    run_id = str(db.run.id)
    await activities.prepare(run_id)
    with pytest.raises(ApplicationError, match="USD"):
        await activities.read(run_id)
    assert not integrations.mutations
    assert not model.calls


@pytest.mark.parametrize(
    "reason", ["spending_limit", "provider_result_unavailable", "billing_refused"]
)
async def test_unavailable_account_read_keeps_its_reason(reason):
    activities, db, storage, integrations, model = monitor_fixture()
    run_id = str(db.run.id)
    await activities.prepare(run_id)

    async def unavailable(*args, **kwargs):
        return {
            "status": "unavailable",
            "reason": reason,
            "billing_error_code": "unmetered_operation" if reason == "billing_refused" else None,
        }

    activities._ads = unavailable
    with pytest.raises(ApplicationError, match=reason) as caught:
        await activities.read(run_id)
    assert not integrations.mutations and not model.calls
    await activities.failure(run_id)
    message = db.project_failure.await_args.kwargs["error_message"]
    expected = {
        "spending_limit": "spending limit",
        "provider_result_unavailable": "provider_result_unavailable",
        "billing_refused": "unmetered_operation",
    }[reason]
    assert expected in message
    assert "account read" in message and "model call" not in message
    assert caught.value.non_retryable is (reason != "provider_result_unavailable")
