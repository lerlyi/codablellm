from pathlib import Path
from typing import List

import pytest

from codablellm.core.function import DecompiledFunction
from codablellm.core import *


def test_set_and_get_decompiler(monkeypatch: pytest.MonkeyPatch):
    """
    Ensures `decompiler.set()` and `decompiler.get()` functions correctly register and return the active decompiler.
    """

    def mock_create():
        return object()

    monkeypatch.setattr("codablellm.core.decompiler.create_decompiler", mock_create)
    decompiler.set("FakeDecompiler", (Path("/fake/path"), "FakeClass"))
    name, (path, symbol) = decompiler.get()
    assert name == "FakeDecompiler"
    assert path == Path("/fake/path")
    assert symbol == "FakeClass"


def test_pseudo_strip(
    mock_decompiler: Decompiler, dummy_decompiled_function: DecompiledFunction
):
    """
    Validates that `pseudo_strip()` replaces original function symbols with anonymized placeholders.
    """
    stripped = decompiler.pseudo_strip(mock_decompiler, dummy_decompiled_function)
    assert "FUN_400080" in stripped.definition or "FUN_400080" in stripped.assembly


def test_create_decompiler_import(monkeypatch: pytest.MonkeyPatch):
    """
    Verifies that `create_decompiler()` correctly loads and initializes a class from the dynamic import.
    """

    class MockDecompiler: ...

    monkeypatch.setattr(
        "codablellm.core.decompiler.dynamic_import", lambda _: MockDecompiler
    )
    instance = decompiler.create_decompiler()
    assert isinstance(instance, MockDecompiler)


def test_decompile_task_runs_with_symbol_removal(
    mock_decompiler: Decompiler,
    dummy_decompiled_function: DecompiledFunction,
):
    """
    Checks if `decompile_task` correctly calls `decompile_stripped()` when a symbol remover is specified.
    """

    result = decompiler.decompile_task.fn(
        mock_decompiler, dummy_decompiled_function.path, "pseudo-strip"
    )
    assert isinstance(result, list)
    assert result[0].uid == "test"


def test_decompile(
    monkeypatch: pytest.MonkeyPatch,
    mock_decompiler: Decompiler,
    dummy_decompiled_function: DecompiledFunction,
    tmp_path: Path,
):
    """ "
    Tests the high-level `decompile` function's return decompiled functions.
    """

    class MockPath:
        def __init__(self, path: str) -> None:
            self.path = path

        def is_dir(self) -> bool:
            return True

        def rglob(self, *args, **kwargs) -> List[Path]:
            return [Path("test1"), Path("test2")]

        def glob(self, *args, **kwargs) -> List[Path]:
            return self.rglob(*args, **kwargs)

        def mkdir(self, *args, **kwargs) -> None:
            Path(self.path).mkdir(*args, **kwargs)

    monkeypatch.setattr("codablellm.core.decompiler.Path", MockPath)
    monkeypatch.setattr(
        "codablellm.core.decompiler.create_decompiler",
        lambda *args, **kwargs: mock_decompiler,
    )
    monkeypatch.setattr(
        "codablellm.core.decompiler.is_binary", lambda *args, **kwargs: True
    )

    class MockFuture:
        def result(self, *args, **kwargs) -> List[DecompiledFunction]:
            return [dummy_decompiled_function]

    monkeypatch.setattr(
        "codablellm.core.decompiler.decompile_task.submit",
        lambda *a, **kw: MockFuture(),
    )

    path = tmp_path / "test_dir"
    config = DecompileConfig(recursive=True)
    results = decompiler.decompile(path, config=config)
    assert isinstance(results, list)
    assert results[0].name == "test_function"
