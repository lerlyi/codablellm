from contextlib import contextmanager, nullcontext
import logging
import subprocess
from typing import Any, Callable, Generator, Literal, Optional, Sequence, Union

from codablellm.core import utils
from codablellm.core.dashboard import Progress
from codablellm.core.function import SourceFunction
from codablellm.dataset import DecompiledCodeDataset, SourceCodeDataset


Command = Union[str, Sequence[Any]]

logger = logging.getLogger('codablellm')


def add_command_args(command: Command, *args: Any) -> Command:
    return [*command, *args] if not isinstance(Command, str) else [command, *args]


def chain_command(command: Command, other: Command) -> Command:
    return add_command_args(command, ';', other)


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


create_source_dataset = SourceCodeDataset.from_repository
create_decompiled_dataset = DecompiledCodeDataset.from_repository


def compile_dataset(path: utils.PathLike, bins: Sequence[utils.PathLike], build_command: Command,
                    max_extractor_workers: Optional[int] = None,
                    max_decompiler_workers: Optional[int] = None,
                    transform: Optional[Callable[[SourceFunction],
                                                 SourceFunction]] = None,
                    generation_mode: Optional[Literal['path',
                                                      'temp',
                                                      'temp-append']] = None,
                    cleanup_command: Optional[Command] = None,
                    ignore_build_errors: Optional[bool] = None,
                    ignore_cleanup_errors: Optional[bool] = None,
                    progress: Optional[Literal['accurate',
                                               'lazy']] = None,
                    repo_arg_with: Optional[Literal['build',
                                                    'cleanup', 'both']] = None,
                    parallel_build: bool = True) -> DecompiledCodeDataset:
    if repo_arg_with == 'build' or repo_arg_with == 'both':
        build_command = add_command_args(build_command, path)
    if cleanup_command and (repo_arg_with == 'cleanup' or repo_arg_with == 'both'):
        cleanup_command = add_command_args(cleanup_command, path)
    with manage(build_command, **utils.resolve_kwargs(cleanup_command=cleanup_command,
                                                      ignore_build_errors=ignore_build_errors,
                                                      ignore_cleanup_errors=ignore_cleanup_errors,
                                                      show_progress=progress)):
        if progress:
            accurate_progress = True if progress == 'accurate' else False
        else:
            accurate_progress = None
        return create_decompiled_dataset(path, bins, **utils.resolve_kwargs(max_extractor_workers=max_extractor_workers,
                                                                            max_decompiler_workers=max_decompiler_workers,
                                                                            accurate_progress=accurate_progress))
