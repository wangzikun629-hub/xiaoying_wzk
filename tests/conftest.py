import pytest

from campaign_planner.runner import run
from campaign_planner.schemas import parse_time, validate_request
from campaign_planner.storage import Storage
from campaign_planner.tools import Engine
from campaign_planner.trace import Trace


@pytest.fixture
def request_data():
    return dict(theme="毕业季校园影像征集", budget=10, deadline="2030-06-01T13:00:00+08:00")


@pytest.fixture
def engine(tmp_path, request_data):
    now = parse_time("2030-06-01T10:00:00+08:00")
    request, _ = validate_request(request_data, now)
    state = dict(
        request=request, status="running", mode="mock", clock_mode="simulated",
        clock_anchor=now.isoformat(), elapsed_minutes=0, spent=0, results={}, materials={},
        attempts=[], plans=[], quotes={}, fault_counts={}, active_run_id="test", runs=[],
    )
    store = Storage(tmp_path / "guard.sqlite")
    store.put(state)
    instance = Engine(store, state, Trace(tmp_path / "trace.jsonl", "mock"))
    instance.execute("search_materials", {"query": request["theme"]})
    yield instance
    store.close()


@pytest.fixture
def invoke(tmp_path, request_data):
    sequence = 0

    def call(changes=None, **kwargs):
        nonlocal sequence
        sequence += 1
        raw = dict(request_data, **(changes or {}))
        return run(
            raw,
            db=kwargs.pop("db", tmp_path / "state.sqlite"),
            output=tmp_path / str(sequence),
            now="2030-06-01T10:00:00+08:00",
            **kwargs,
        )

    return call
