from pathlib import Path
from typing import Sequence

import pytest

from codablellm.core.decompiler import Decompiler
from codablellm.core.function import DecompiledFunction
from codablellm.core.utils import PathLike


@pytest.fixture
def dummy_decompiled_function(tmp_path: Path):
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
