import pytest

from campaign_planner.runner import run


@pytest.fixture
def request_data():
    return dict(theme="毕业季校园影像征集", budget=10, deadline="2030-06-01T13:00:00+08:00")


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
