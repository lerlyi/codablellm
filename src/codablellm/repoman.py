from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
import logging
import subprocess
from typing import Any, Callable, Generator, Iterable, Literal, Optional, Sequence, Set, Union

from rich.prompt import Prompt

from codablellm.core import utils
from codablellm.core.dashboard import Progress
from codablellm.core.function import SourceFunction
from codablellm.dataset import DecompiledCodeDataset, SourceCodeDataset


Command = Union[str, Sequence[Any]]
CommandErrorHandler = Literal['interactive', 'ignore', 'none']

logger = logging.getLogger('codablellm')


def add_command_args(command: Command, *args: Any) -> Command:
    return [*command, *args] if not isinstance(Command, str) else [command, *args]


def execute_command(command: Command, error_handler: CommandErrorHandler = 'none', ignore_errors: bool = False,
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
        try:
            subprocess.run(command, capture_output=True, text=True, shell=True,
                           check=True)
        except subprocess.CalledProcessError:
            logger.error(f'Command failed: {command}')
            if error_handler == 'interactive':
                result = Prompt.ask('A command error occurred. You can manually fix the issue and '
                                    'retry, ignore the error to continue, or abort the process. '
                                    'How would you like to proceed?',
                                    choices=['retry', 'ignore', 'abort'],
                                    case_sensitive=False, default='retry')
                if result == 'retry':
                    execute_command(command, error_handler=error_handler,
                                    task=task)
                elif result == 'abort':
                    raise
        else:
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


@dataclass
class ManageConfig:
    cleanup_command: Optional[Command] = None
    build_error_handling: CommandErrorHandler = 'interactive'
    cleanup_error_handling: CommandErrorHandler = 'ignore'
    show_progress: Optional[bool] = None


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
                    exclude_subpaths: Optional[Iterable[utils.PathLike]] = None,
                    exclusive_subpaths: Optional[Iterable[utils.PathLike]] = None,
                    checkpoint: Optional[int] = None,
                    use_checkpoint: Optional[bool] = None) -> DecompiledCodeDataset:
    if repo_arg_with == 'build' or repo_arg_with == 'both':
        build_command = add_command_args(build_command, path)
    if cleanup_command and (repo_arg_with == 'cleanup' or repo_arg_with == 'both'):
        cleanup_command = add_command_args(cleanup_command, path)
    if progress:
        accurate_progress = progress == 'accurate'
    else:
        accurate_progress = None
    if transform:
        modified_source_dataset = create_source_dataset(path,
                                                        generation_mode='path' if generation_mode == 'path' else 'temp',
                                                        transform=transform,
                                                        delete_temp=False,
                                                        **utils.resolve_kwargs(max_workers=max_extractor_workers,
                                                                               accurate_progress=accurate_progress,
                                                                               exclude_subpaths=exclude_subpaths,
                                                                               exclusive_subpaths=exclusive_subpaths,
                                                                               checkpoint=checkpoint,
                                                                               use_checkpoint=use_checkpoint
                                                                               ))
        with manage(build_command, **utils.resolve_kwargs(cleanup_command=cleanup_command,
                                                          ignore_build_errors=ignore_build_errors,
                                                          ignore_cleanup_errors=ignore_cleanup_errors,
                                                          show_progress=progress)):
            modified_decompiled_dataset = DecompiledCodeDataset.from_source_code_dataset(modified_source_dataset, bins,
                                                                                         **utils.resolve_kwargs(max_workers=max_decompiler_workers,))
            if generation_mode == 'temp' or generation_mode == 'path':
                return modified_decompiled_dataset
            return DecompiledCodeDataset.concat(modified_decompiled_dataset, compile_dataset(path, bins, build_command,
                                                                                             max_extractor_workers=max_extractor_workers,
                                                                                             max_decompiler_workers=max_decompiler_workers,
                                                                                             cleanup_command=cleanup_command,
                                                                                             ignore_build_errors=ignore_build_errors,
                                                                                             ignore_cleanup_errors=ignore_cleanup_errors,
                                                                                             progress=progress,
                                                                                             repo_arg_with=repo_arg_with))
    else:
        with manage(build_command, **utils.resolve_kwargs(cleanup_command=cleanup_command,
                                                          ignore_build_errors=ignore_build_errors,
                                                          ignore_cleanup_errors=ignore_cleanup_errors,
                                                          show_progress=progress)):
            return create_decompiled_dataset(path, bins, **utils.resolve_kwargs(max_extractor_workers=max_extractor_workers,
                                                                                max_decompiler_workers=max_decompiler_workers,
                                                                                accurate_progress=accurate_progress,
                                                                                ))
