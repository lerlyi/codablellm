from pathlib import Path
from subprocess import CalledProcessError
import pytest

from codablellm.core.extractor import ExtractConfig
from codablellm.repoman import Command, ManageConfig, compile_dataset, manage


def test_manage(failing_command: Command) -> None:
    with pytest.raises(CalledProcessError):
        with manage('make', ManageConfig(
            cleanup_command=failing_command,
            cleanup_error_handling='none'
        )):
            pass


def test_compile_dataset(c_repository: Path, c_bin: Path) -> None:
    dataset = compile_dataset(c_repository, [c_bin], 'make',
                              extract_config=ExtractConfig(
                                  transform=lambda s: s.with_definition('')
    ),
        generation_mode='temp-append')
