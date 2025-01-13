'''
High-level functionality for creating code datasets from source code repositories.
'''

from contextlib import contextmanager, nullcontext
from dataclasses import asdict, dataclass
import logging
import subprocess
from tempfile import NamedTemporaryFile
from typing import Any, Generator, Literal, Optional, Sequence, Tuple, Union

from rich.prompt import Prompt

from codablellm.core import utils
from codablellm.core.dashboard import Progress
from codablellm.core.extractor import ExtractConfig
from codablellm.core.function import DecompiledFunction
from codablellm.dataset import (
    DatasetGenerationMode, DecompiledCodeDataset, DecompiledCodeDatasetConfig, SourceCodeDataset,
    SourceCodeDatasetConfig
)


Command = Union[Any, Sequence[Any]]
'''
A CLI command.
'''

CommandErrorHandler = Literal['interactive', 'ignore', 'none']
'''
Defines the strategies for handling errors encountered during the execution of a CLI command.

Supported Error Handlers:
    - **`ignore`**: The CLI command error is ignored, and execution continues without interruption.
    - **`none`**: An exception is raised immediately upon encountering the CLI error.
    - **`interactive`**: The user is prompted to resolve the error manually, allowing for
    interactive handling of the issue.
'''

logger = logging.getLogger('codablellm')


def add_command_args(command: Command, *args: Any) -> Command:
    '''
    Appends additional arguments to a CLI command.

    Parameters:
        command: The CLI command to append.
        args: Additional arguments to append to the command.

    Returns:
        The updated command with the appended arguments.
    '''
    return [*command, *args] if not isinstance(command, Sequence) else [command, *args]


def execute_command(command: Command, error_handler: CommandErrorHandler = 'none',
                    task: Optional[str] = None, show_progress: bool = True) -> None:
    '''
    Executes a CLI command.

    Parameters:
        command: The CLI command to be executed.
        error_handler: Specifies how to handle errors during command execution.
        task: An optional description of the task being performed, used for logging and displaying progress information.
        show_progress: If `True`, a progress bar is displayed while the command is executing.
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
                    error_handler = 'none'
            if error_handler == 'none':
                raise
        else:
            logger.info(f'Successfully executed "{command}"')


def build(command: Command, error_handler: Optional[CommandErrorHandler] = None,
          show_progress: Optional[bool] = None) -> None:
    '''
    Builds a local repository using a specified CLI command.

    Parameters:
        command: The CLI command to execute for building the repository.
        error_handler: Specifies how to handle errors during the build process.
        show_progress: Specifies whether to display a progress bar during the build process.
    '''
    execute_command(command, task='Building repository...',
                    **utils.resolve_kwargs(error_handler=error_handler,
                                           show_progress=show_progress))


def cleanup(command: Command, error_handler: Optional[CommandErrorHandler] = None,
            show_progress: Optional[bool] = None) -> None:
    '''
    Cleans up build artifacts of a local repository using a specified CLI command.

    Parameters:
        command: The CLI command to execute for cleaning up the repository.
        error_handler: Specifies how to handle errors during the cleanup process. 
        show_progress: Specifies whether to display a progress bar during the cleanup process. 
    '''
    execute_command(command, task='Cleaning up repository...',
                    **utils.resolve_kwargs(error_handler=error_handler,
                                           show_progress=show_progress))


@dataclass(frozen=True)
class ManageConfig:
    '''
    Configuration settings for managing a built local repository.
    '''
    cleanup_command: Optional[Command] = None
    '''
    An optional CLI command to clean up the build artifacts of the repository.
    '''
    build_error_handling: CommandErrorHandler = 'interactive'
    '''
    Specifies how to handle errors during the build process.
    '''
    cleanup_error_handling: CommandErrorHandler = 'ignore'
    '''
    Specifies how to handle errors during the cleanup process, if `cleanup_command` is provided.
    '''
    show_progress: Optional[bool] = None
    '''
    Indicates whether to display a progress bar during both the build and cleanup processes. 
    '''


@contextmanager
def manage(build_command: Command,
           config: ManageConfig = ManageConfig()) -> Generator[None, None, None]:
    '''
    Builds a local repository and optionally cleans up the build artifacts using a context manager.

    Parameters:
        build_command: The CLI command used to build the repository.
        config: Configuration settings for managing the repository.

    Returns:
        A context manager that builds the repository upon entering and optionally cleans up build artifacts upon exiting, based on the provided configuration.
    '''
    build(build_command, error_handler=config.build_error_handling,
          show_progress=config.show_progress)
    yield
    if config.cleanup_command:
        cleanup(config.cleanup_command, error_handler=config.cleanup_error_handling,
                show_progress=config.show_progress)


create_source_dataset = SourceCodeDataset.from_repository
'''
Creates a `SourceCodeDataset` from a repository.
'''

create_decompiled_dataset = DecompiledCodeDataset.from_repository
'''
Creates a `DecompiledCodeDataset` from a repository.
'''


def compile_dataset(path: utils.PathLike, bins: Sequence[utils.PathLike], build_command: Command,
                    manage_config: ManageConfig = ManageConfig(),
                    extract_config: ExtractConfig = ExtractConfig(),
                    dataset_config: DecompiledCodeDatasetConfig = DecompiledCodeDatasetConfig(),
                    generation_mode: DatasetGenerationMode = 'temp',
                    repo_arg_with: Optional[Literal['build',
                                                    'cleanup', 'both']] = None
                    ) -> DecompiledCodeDataset:
    '''
    Builds a local repository and creates a `DecompiledCodeDataset` by decompiling the specified binaries.

    This function automates the process of building a repository, decompiling its binaries, 
    and generating a dataset of decompiled functions mapped to their potential source functions. 
    It supports flexible configuration for repository management, source code extraction, and 
    dataset generation.

    Example:
            ```py
            compile_dataset('path/to/my/repository',
                                [
                                'path/to/my/repository/bin1.exe',
                                'path/to/my/repository/bin2.exe'
                                ],
                                'make',
                                manage_config=ManageConfig(
                                    cleanup_command='make clean'
                                )
                                extract_config=ExtractConfig(
                                    transform=remove_comments
                                ),
                                dataset_config=DecompiledCodeDatasetConfig(
                                    strip=True
                                ),
                                generation_mode='path'
                            )
            ```

            The above example creates a decompiled code dataset from 
            `path/to/my/repository`. It removes all comments from the extracted source 
            code functions using the specified transform (`remove_comments`), builds the repository
            with `make`, decompiles, the binaries `bin1.exe` and `bin2.exe`, strips symbols after
            decompilation, and finally cleans up the repository with `make clean`.

    Parameters:
        path: Path to the local repository to generate the dataset from.
        bins: A sequence of paths to the built binaries of the repository that should be decompiled.
        build_command: The CLI command used to build the repository.
        manage_config: Configuration settings for managing the repository.
        extract_config: Configuration settings for extracting source code functions.
        dataset_config: Configuration settings for generating the decompiled code dataset.
        repo_arg_with: If specified, appends the path to the repository to the `build_command`, `cleanup_command`, or both. This option is mainly useful when `generation_mode` is set to `'temp'` or `'temp-append'`, as it ensures that the commands operate on the temporary directory containing the copied repository.

    Returns:
        The generated dataset containing mappings of decompiled functions to their potential source code functions.
'''
    def try_transform_metadata(decompiled_function: DecompiledFunction,
                               source_functions: SourceCodeDataset,
                               other_dataset: DecompiledCodeDataset) -> Tuple[DecompiledFunction, SourceCodeDataset]:
        # Try to add transformed metadata to the decompiled function if it's in the other dataset
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

    # Add path to build/cleanup commands
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
        # Create a modified source code dataset with transformed code
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
            # Compile repository
            with manage(build_command, config=manage_config):
                modified_decompiled_dataset = DecompiledCodeDataset.from_source_code_dataset(modified_source_dataset, bins,
                                                                                             config=dataset_config)
                if generation_mode == 'temp' or generation_mode == 'path':
                    logger.debug('Removing backup modified source dataset '
                                 f'"{modified_source_dataset_file.name}"')
                    return modified_decompiled_dataset
                # Duplicate the extract config without a transform to append
                extract_config_dict = asdict(extract_config)
                extract_config_dict['transform'] = None
                no_transform_extract = ExtractConfig(**extract_config_dict)
                # Compile dataset without transform
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
