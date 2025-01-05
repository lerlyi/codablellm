from pathlib import Path
import subprocess
from typing import Any, List, Union
from pytest import MonkeyPatch, TempPathFactory, fixture

from codablellm.repoman import Command

FAILING_COMMAND = 'FAILED'


@fixture(autouse=True)
def mock_subprocess_run(monkeypatch: MonkeyPatch) -> None:

    def run(command: Union[List[str], str], *args, **kwargs) -> Any:
        if isinstance(command, str):
            command = [command]
        if command == [FAILING_COMMAND]:
            raise subprocess.CalledProcessError(1, command)
    monkeypatch.setattr(subprocess, 'run', run)


@fixture()
def failing_command() -> Command:
    return FAILING_COMMAND


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
