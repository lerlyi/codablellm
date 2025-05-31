from pathlib import Path
from typing import Sequence

import pytest

from codablellm.core.decompiler import Decompiler
from codablellm.core.function import DecompiledFunction, SourceFunction
from codablellm.core.utils import DynamicSymbol, PathLike


@pytest.fixture
def dummy_decompiled_function(tmp_path: Path) -> DecompiledFunction:
    """
    Provides a reusable mock `DecompiledFunction` instance used across multiple tests.
    """
    return DecompiledFunction(
        uid="test",
        path=tmp_path.with_name("test.exe"),
        name="test_function",
        definition="int test() { return 0; }",
        assembly="test: mov eax, 0",
        architecture="x86_64",
        address=0x400080,
    )


@pytest.fixture
def mock_decompiler(
    dummy_decompiled_function: DecompiledFunction,
) -> Decompiler:
    """
    Provides a mock decompiler class for testing
    """

    class MockDecompiler(Decompiler):
        def decompile(self, path: PathLike) -> Sequence[DecompiledFunction]:
            return [dummy_decompiled_function]

        def get_stripped_function_name(self, address: int) -> str:
            return f"FUN_{address:X}"

    return MockDecompiler()


@pytest.fixture
def dummy_c_file(tmp_path: Path) -> Path:
    """
    Provides a reusable C source code file used across multiple tests.
    """
    tmp_path = tmp_path / "test.c"
    tmp_path.write_text("int test() { return 0; }")
    return tmp_path


@pytest.fixture
def dummy_transform_symbol(tmp_path: Path) -> DynamicSymbol:
    """
    Provides a reusable Python file with a transform used across multiple tests.
    """
    tmp_path = tmp_path / "transform.py"
    tmp_path.write_text(
        (
            "def dummy_transform(sf):"
            "return sf.with_definition("
            '    "int transformed_function(int arg) { return 1; }",'
            '    name="transformed_function",'
            ")"
        )
    )
    return (tmp_path, "dummy_transform")
