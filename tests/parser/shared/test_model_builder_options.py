"""
Unit tests for model_builder_options helper flows.
"""

import os

import pytest

from t4t.parser.shared import model_builder_options as mbo


@pytest.fixture(autouse=True)
def patch_builder(monkeypatch):
    calls: list[tuple[dict, str]] = []

    def _fake_build_and_print_model(metadata, file_path):
        calls.append((metadata, file_path))
        return {"model_metadata": {"table_name": "x"}}

    monkeypatch.setattr(mbo, "build_and_print_model", _fake_build_and_print_model)
    return calls


def test_model_builder_executes_only_in_main_with_metadata(monkeypatch, patch_builder):
    frame = type("F", (), {})()
    back = type("B", (), {})()
    back.f_globals = {
        "__name__": "__main__",
        "__file__": "/tmp/model.py",
        "metadata": {"schema": []},
    }
    frame.f_back = back
    monkeypatch.setattr("inspect.currentframe", lambda: frame)

    mbo.ModelBuilder()
    assert len(patch_builder) == 1
    assert patch_builder[0][1] == os.path.abspath("/tmp/model.py")


def test_model_builder_skips_when_not_main(monkeypatch, patch_builder):
    frame = type("F", (), {})()
    back = type("B", (), {})()
    back.f_globals = {"__name__": "not_main", "__file__": "/tmp/model.py", "metadata": {"a": 1}}
    frame.f_back = back
    monkeypatch.setattr("inspect.currentframe", lambda: frame)

    mbo.ModelBuilder()
    assert patch_builder == []


def test_build_returns_model_only_when_main(monkeypatch, patch_builder):
    frame = type("F", (), {})()
    back = type("B", (), {})()
    back.f_globals = {
        "__name__": "__main__",
        "__file__": "/tmp/model.py",
        "metadata": {"materialization": "table"},
    }
    frame.f_back = back
    monkeypatch.setattr("inspect.currentframe", lambda: frame)

    result = mbo.build()
    assert result is not None
    assert len(patch_builder) == 1

    back.f_globals["__name__"] = "imported_module"
    assert mbo.build() is None


def test_setup_auto_build_registers_and_executes_immediately(monkeypatch, patch_builder):
    frame = type("F", (), {})()
    back = type("B", (), {})()
    back.f_globals = {
        "__name__": "__main__",
        "__file__": "/tmp/auto.py",
        "metadata": {"schema": [{"name": "id"}]},
    }
    frame.f_back = back
    monkeypatch.setattr("inspect.currentframe", lambda: frame)

    registered = []
    monkeypatch.setattr("atexit.register", lambda fn: registered.append(fn))

    mbo.setup_auto_build()
    assert len(registered) == 1
    # immediate path when metadata already exists
    assert len(patch_builder) == 1

    # and delayed function is also callable
    registered[0]()
    assert len(patch_builder) == 2
