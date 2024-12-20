from contextlib import contextmanager, nullcontext
import logging
import subprocess
from typing import Any, Generator, Optional, Sequence, Union

from codablellm.core import utils
from codablellm.core.dashboard import Progress


Command = Union[str, Sequence[Any]]

logger = logging.getLogger('codablellm')


def execute_command(command: Command, ignore_errors: bool = False,
                    task: Optional[str] = None, show_progress: bool = True) -> None:
    '''
    Executes a repository command.

    Parameters:
        cmd: Command to execute.
        ignore_errors: True if any command errors should not be raised.
        task: Optional task description to specify when logging and displaying progress.
        show_progress: True if a progress bar should be displayed while executing the command.
    '''
    if not task:
        task = f'Executing: "{command}"'
    logger.info(task)
    ctx = Progress(f'{task}...') if show_progress else nullcontext()
    with ctx:
        subprocess.run(command, capture_output=True, text=True, shell=True,
                       check=ignore_errors)
    logger.info(f'Successfully executed "{command}"')


def build(command: Command, ignore_errors: Optional[bool] = None,
          show_progress: Optional[bool] = None) -> None:
    execute_command(command, task='Building repository...',
                    **utils.resolve_kwargs(ignore_errors=ignore_errors,
                                           show_progress=show_progress))


def cleanup(command: Command, ignore_errors: Optional[bool] = None,
            show_progress: Optional[bool] = None) -> None:
    execute_command(command, task='Cleaning up repository...',
                    **utils.resolve_kwargs(ignore_errors=ignore_errors,
                                           show_progress=show_progress))


@contextmanager
def manage(build_command: Command, cleanup_command: Optional[Command] = None,
           ignore_build_errors: Optional[bool] = None,
           ignore_cleanup_errors: Optional[bool] = None,
           show_progress: Optional[bool] = None) -> Generator[None, None, None]:
    build(build_command, ignore_errors=ignore_build_errors,
          show_progress=show_progress)
    yield
    if cleanup_command:
        cleanup(cleanup_command, ignore_errors=ignore_cleanup_errors,
                show_progress=show_progress)
