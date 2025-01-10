from pathlib import Path
from subprocess import CalledProcessError
import pytest

from codablellm.repoman import Command, compile_dataset, manage


def test_manage(failing_command: Command) -> None:
    with pytest.raises(CalledProcessError):
        with manage('make', cleanup_command=failing_command):
            pass


def test_compile_dataset(c_repository: Path, c_bin: Path) -> None:
    dataset = compile_dataset(c_repository, [c_bin], 'make',
                              transform=lambda s: s.with_definition(''),
                              generation_mode='temp-append')
