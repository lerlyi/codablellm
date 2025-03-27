import json
from pathlib import Path
import subprocess
from typing import Any, List, Sequence, Union
from pytest import MonkeyPatch, TempPathFactory, fixture

from codablellm.core import utils
from codablellm.core import decompiler
from codablellm.core.decompiler import Decompiler
from codablellm.core.decompiler import _decompile
from codablellm.core.function import DecompiledFunction, DecompiledFunctionJSONObject

FAILING_COMMAND = 'FAILED'


@fixture(autouse=True)
def mock_subprocess_check_output(monkeypatch: MonkeyPatch) -> None:

    def check_output(command: Union[List[str], str], *args, **kwargs) -> Any:
        if isinstance(command, str):
            command = [command]
        if command == [FAILING_COMMAND]:
            raise subprocess.CalledProcessError(1, command)
    monkeypatch.setattr(subprocess, 'check_output', check_output)


@fixture()
def failing_command() -> utils.Command:
    return FAILING_COMMAND


FAILING_BIN = 'FAILED'


class MockDecompiler(Decompiler):

    def decompile(self, path: utils.PathLike) -> Sequence[DecompiledFunction]:
        print('MockDecompiler called')
        if path == FAILING_BIN:
            raise subprocess.CalledProcessError(1, path)
        path = Path(path)
        decompiled_funcs_json: List[DecompiledFunctionJSONObject] = \
            json.loads(path.read_text())
        return [DecompiledFunction.from_json(func) for func in decompiled_funcs_json]


def _decompile(path: utils.PathLike, *args: Any, **kwargs: Any) -> Sequence[DecompiledFunction]:
    return MockDecompiler().decompile(path)


@fixture(autouse=True)
def mock_decompile(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(decompiler, '_decompile', _decompile)


@fixture(scope='session')
def c_repository(tmp_path_factory: TempPathFactory) -> Path:

    def create_file(file: Path, func_range: range) -> None:
        file.write_text('#include <stdio.h>\n' +
                        '\n'.join(f'\nvoid function{n}() {{' +
                                  f'\n\tprintf("Function {n} in {file.name}\\n");' +
                                  '\n}' for n in func_range))

    path = tmp_path_factory.mktemp('c_repository')
    create_file(path / 'file1.c', range(1, 4))
    create_file(path / 'file2.c', range(4, 7))
    create_file(path / 'file3.c', range(7, 9))
    return path


@fixture(scope='session')
def c_bin(tmp_path_factory: TempPathFactory) -> Path:

    def create_file(file: Path, func_range: range) -> None:
        # This is what is causing the tests to break
        file.write_text(json.dumps([DecompiledFunction(DecompiledFunction.create_uid(path, f'function{f}'),
                                                       file,
                                                       f'function{f}',
                                                       f'void function{f}: ' +
                                                       '\n<decompiled_def>',
                                                       f'function{f}:' +
                                                       '\n<decompiled_asm>',
                                                       'x86_64').to_json() for f in func_range]))
    path = tmp_path_factory.mktemp('c_bins')
    c_bin = path / 'out.lib'
    create_file(c_bin, range(1, 9))
    return c_bin
