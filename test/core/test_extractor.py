from pathlib import Path

import pytest

from codablellm.core import *
from codablellm.core.utils import DynamicSymbol
from codablellm.languages.c import CExtractor


def test_register_and_unregister(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "codablellm.extractor.create_extractor", lambda *args, **kwargs: CExtractor()
    )
    extractor.register("FakeLang", (Path("/fake/path"), "FakeExtractor"))
    assert any(r.language == "FakeLang" for r in extractor.get_registered())
    extractor.unregister("FakeLang")
    assert all(r.language != "FakeLang" for r in extractor.get_registered())


def test_unregister_all(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "codablellm.extractor.create_extractor", lambda *args, **kwargs: CExtractor()
    )
    extractor.register("LangA", (Path("/fake/path"), "ExtractorA"))
    extractor.register("LangB", (Path("/fake/path"), "ExtractorB"))
    extractor.unregister_all()
    assert extractor.get_registered() == []


def test_set_registered(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "codablellm.extractor.create_extractor", lambda *args, **kwargs: CExtractor()
    )
    extractor.set_registered({"LangX": (Path("/some/file.py"), "MockExtractor")})
    assert any(r.language == "LangX" for r in extractor.get_registered())


@pytest.mark.skip(reason="Race condition happening when suite is ran in parallel")
def test_create_extractor(monkeypatch: pytest.MonkeyPatch):
    class DummyExtractor(Extractor):
        def extract(self, *args, **kwargs):
            return []

        def get_extractable_files(self, *args, **kwargs):
            return set()

    monkeypatch.setattr(
        "codablellm.extractor.dynamic_import", lambda symbol: DummyExtractor
    )
    my_extractor = extractor.create_extractor("C")
    assert isinstance(my_extractor, Extractor)


def test_extract_file(dummy_c_file: Path):
    class DummyExtractor(Extractor):
        def extract(self, *args, **kwargs):
            definition = dummy_c_file.read_text()
            return [
                SourceFunction.from_source(
                    dummy_c_file, "C", definition, "test", 0, len(definition)
                )
            ]

        def get_extractable_files(self, *args, **kwargs):
            return {dummy_c_file}

    result = extractor.extract_file_task.fn(DummyExtractor(), dummy_c_file, None)
    assert isinstance(result, list)
    assert len(result) == 1
    (func,) = result
    assert func.uid == f"{func.path.name}::{func.name}"

@pytest.mark.skip(reason="Race condition happening when suite is ran in parallel")
def test_apply_transform_task(
    dummy_c_file: Path, dummy_transform_symbol: DynamicSymbol
):
    result = extractor.extract(
        dummy_c_file, config=ExtractConfig(transform=dummy_transform_symbol)
    )
    assert isinstance(result, list)
    assert len(result) == 1
    (func,) = result
    assert func.uid == f"{func.path.name}::{func.name}"
