from contextlib import contextmanager, nullcontext
from dataclasses import asdict, dataclass
import logging
import subprocess
from tempfile import NamedTemporaryFile
from typing import Any, Callable, Dict, Generator, Iterable, Literal, Optional, Sequence, Set, Tuple, Union

from rich.prompt import Prompt

from codablellm.core import utils
from codablellm.core.dashboard import Progress
from codablellm.core.extractor import ExtractConfig
from codablellm.core.function import DecompiledFunction, SourceFunction
from codablellm.dataset import DecompiledCodeDataset, DecompiledCodeDatasetConfig, SourceCodeDataset, SourceCodeDatasetConfig


Command = Union[str, Sequence[Any]]
CommandErrorHandler = Literal['interactive', 'ignore', 'none']

logger = logging.getLogger('codablellm')


def add_command_args(command: Command, *args: Any) -> Command:
    return [*command, *args] if not isinstance(Command, str) else [command, *args]


def execute_command(command: Command, error_handler: CommandErrorHandler = 'none',
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
                raise
        else:
            logger.info(f'Successfully executed "{command}"')


def build(command: Command, error_handler: CommandErrorHandler = 'none',
          show_progress: Optional[bool] = None) -> None:
    execute_command(command, task='Building repository...',
                    **utils.resolve_kwargs(error_handler=error_handler,
                                           show_progress=show_progress))


def cleanup(command: Command, error_handler: CommandErrorHandler = 'none',
            show_progress: Optional[bool] = None) -> None:
    execute_command(command, task='Cleaning up repository...',
                    **utils.resolve_kwargs(error_handler=error_handler,
                                           show_progress=show_progress))


@dataclass(frozen=True)
class ManageConfig:
    cleanup_command: Optional[Command] = None
    build_error_handling: CommandErrorHandler = 'interactive'
    cleanup_error_handling: CommandErrorHandler = 'ignore'
    show_progress: Optional[bool] = None


@contextmanager
def manage(build_command: Command,
           config: ManageConfig = ManageConfig()) -> Generator[None, None, None]:
    build(build_command, error_handler=config.build_error_handling,
          show_progress=config.show_progress)
    yield
    if config.cleanup_command:
        cleanup(config.cleanup_command, error_handler=config.cleanup_error_handling,
                show_progress=config.show_progress)


create_source_dataset = SourceCodeDataset.from_repository
create_decompiled_dataset = DecompiledCodeDataset.from_repository


def compile_dataset(path: utils.PathLike, bins: Sequence[utils.PathLike], build_command: Command,
                    manage_config: ManageConfig = ManageConfig(),
                    extract_config: ExtractConfig = ExtractConfig(),
                    dataset_config: DecompiledCodeDatasetConfig = DecompiledCodeDatasetConfig(),
                    generation_mode: Literal['path',
                                             'temp', 'temp-append'] = 'temp',
                    repo_arg_with: Optional[Literal['build',
                                                    'cleanup', 'both']] = None
                    ) -> DecompiledCodeDataset:
    def try_transform_metadata(decompiled_function: DecompiledFunction,
                               source_functions: SourceCodeDataset,
                               other_dataset: DecompiledCodeDataset) -> Tuple[DecompiledFunction, SourceCodeDataset]:
        matched_decompiled_function, matched_source_functions = \
            other_dataset.get(decompiled_function,  # type: ignore
                              default=(None, None))
        if matched_decompiled_function and matched_source_functions:
            decompiled_function = decompiled_function.with_metadata({
                **decompiled_function.metadata,
                'transformed_assembly': matched_decompiled_function.assembly,
                'transformed_decompiled_definition': matched_decompiled_function.definition,
            })
            source_functions = SourceCodeDataset(s.with_metadata({
                'transformed_source_definitions': s.definition,
                'transformed_class_names': s.class_name,
                **s.metadata
            }) for s in matched_source_functions.values())
        return decompiled_function, source_functions

    if repo_arg_with == 'build' or repo_arg_with == 'both':
        build_command = add_command_args(build_command, path)
    if manage_config.cleanup_command and (repo_arg_with == 'cleanup' or repo_arg_with == 'both'):
        cleanup_command = add_command_args(manage_config.cleanup_command, path)
        manage_config_dict = asdict(manage_config)
        manage_config_dict['cleanup_command'] = cleanup_command
        manage_config = ManageConfig(**manage_config_dict)
    else:
        cleanup_command = manage_config.cleanup_command
    if extract_config.transform:
        modified_source_dataset = create_source_dataset(path,
                                                        config=SourceCodeDatasetConfig(
                                                            generation_mode='path' if generation_mode == 'path' else 'temp',
                                                            delete_temp=False,
                                                            extract_config=extract_config
                                                        ))
        with NamedTemporaryFile('w+', prefix='modified_source_dataset',
                                suffix='.json',
                                delete=False) as modified_source_dataset_file:
            modified_source_dataset_file.close()
            logger.info('Saving backup modified source dataset as '
                        f'"{modified_source_dataset_file.name}"')
            modified_source_dataset.save_as(modified_source_dataset_file.name)
            with manage(build_command, config=manage_config):
                modified_decompiled_dataset = DecompiledCodeDataset.from_source_code_dataset(modified_source_dataset, bins,
                                                                                             config=dataset_config)
                if generation_mode == 'temp' or generation_mode == 'path':
                    logger.debug('Removing backup modified source dataset '
                                 f'"{modified_source_dataset_file.name}"')
                    return modified_decompiled_dataset
                extract_config_dict = asdict(extract_config)
                extract_config_dict['transform'] = None
                no_transform_extract = ExtractConfig(**extract_config_dict)
                original_decompiled_dataset = compile_dataset(path, bins, build_command,
                                                              manage_config=manage_config,
                                                              extract_config=no_transform_extract,
                                                              dataset_config=dataset_config,
                                                              repo_arg_with=repo_arg_with,
                                                              generation_mode='path')
                return DecompiledCodeDataset(try_transform_metadata(d, s, modified_decompiled_dataset)
                                             for d, s in original_decompiled_dataset.values())
    else:
        with manage(build_command, config=manage_config):
            return create_decompiled_dataset(path, bins, extract_config=extract_config,
                                             dataset_config=dataset_config)
