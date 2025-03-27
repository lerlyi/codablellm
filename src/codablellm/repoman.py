'''
High-level functionality for creating code datasets from source code repositories.
'''

from contextlib import contextmanager, nullcontext
from dataclasses import asdict, dataclass
import logging
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Final, Generator, Literal, Optional, Sequence, Tuple

from codablellm.core import utils
from codablellm.core.dashboard import Progress
from codablellm.core.extractor import ExtractConfig
from codablellm.core.function import DecompiledFunction
from codablellm.dataset import (
    DatasetGenerationMode, DecompiledCodeDataset, DecompiledCodeDatasetConfig, SourceCodeDataset,
    SourceCodeDatasetConfig
)

logger = logging.getLogger('codablellm')

REBASED_DIR_ENVIRON_KEY: Final[str] = 'CODABLELLM_REBASED_DIR'
'''
Environment variable key used to expose the rebased directory path to subprocesses.

This is especially useful when running custom build or clean commands that need to
reference the rebased project root dynamically (e.g., using shell expansion like `$CODABLELLM_REBASED_DIR`).

Set automatically when using the `temp` generation mode.
'''


@utils.benchmark_function('Building repository')
def build(command: utils.Command, error_handler: Optional[utils.CommandErrorHandler] = None,
          show_progress: Optional[bool] = None, cwd: Optional[utils.PathLike] = None) -> None:
    '''
    Builds a local repository using a specified CLI command.

    Parameters:
        command: The CLI command to execute for building the repository.
        error_handler: Specifies how to handle errors during the build process.
        show_progress: Specifies whether to display a progress bar during the build process.
        cwd: The working directory to execute the build command in.
    '''
    task = 'Building repository...'
    utils.execute_command(command, task=task,
                          ctx=Progress(
                              task) if show_progress else nullcontext(),
                          **utils.resolve_kwargs(error_handler=error_handler,
                                                 cwd=cwd))


@utils.benchmark_function('Cleaning up repository')
def cleanup(command: utils.Command, error_handler: Optional[utils.CommandErrorHandler] = None,
            show_progress: Optional[bool] = None, cwd: Optional[utils.PathLike] = None) -> None:
    '''
    Cleans up build artifacts of a local repository using a specified CLI command.

    Parameters:
        command: The CLI command to execute for cleaning up the repository.
        error_handler: Specifies how to handle errors during the cleanup process. 
        show_progress: Specifies whether to display a progress bar during the cleanup process.
        cwd: The working directory to execute the build command in.
    '''
    task = 'Cleaning up repository...'
    utils.execute_command(command, task=task,
                          ctx=Progress(
                              task) if show_progress else nullcontext(),
                          **utils.resolve_kwargs(error_handler=error_handler,
                                                 cwd=cwd))


@dataclass(frozen=True)
class ManageConfig:
    '''
    Configuration settings for managing a built local repository.
    '''
    cleanup_command: Optional[utils.Command] = None
    '''
    An optional CLI command to clean up the build artifacts of the repository.
    '''
    build_error_handling: utils.CommandErrorHandler = 'interactive'
    '''
    Specifies how to handle errors during the build process.
    '''
    cleanup_error_handling: utils.CommandErrorHandler = 'ignore'
    '''
    Specifies how to handle errors during the cleanup process, if `cleanup_command` is provided.
    '''
    show_progress: Optional[bool] = None
    '''
    Indicates whether to display a progress bar during both the build and cleanup processes. 
    '''
    run_from: Literal['cwd', 'repo'] = 'repo'
    ''''
    Specifies the working directory from which to run build and clean commands.

    - `repo`: Use the root of the repository as the working directory. This may refer to the original
    repository path or a duplicated temporary copy depending on the generation mode.
    - `cwd`: Use the current working directory at the time the command is run.

    This option controls how relative paths within commands are resolved and can affect the behavior
    of tools that assume a specific project root.
    '''


@contextmanager
def manage(build_command: utils.Command, path: utils.PathLike,
           config: ManageConfig = ManageConfig()) -> Generator[None, None, None]:
    '''
    Builds a local repository and optionally cleans up the build artifacts using a context manager.

    Parameters:
        build_command: The CLI command used to build the repository.
        path: Path to the local repository to manage.
        config: Configuration settings for managing the repository.

    Returns:
        A context manager that builds the repository upon entering and optionally cleans up build artifacts upon exiting, based on the provided configuration.
    '''
    build(build_command, error_handler=config.build_error_handling,
          cwd=path if config.run_from == 'repo' else None,
          show_progress=config.show_progress)
    yield
    if config.cleanup_command:
        cleanup(config.cleanup_command, error_handler=config.cleanup_error_handling,
                cwd=path if config.run_from == 'repo' else None,
                show_progress=config.show_progress)


create_source_dataset = SourceCodeDataset.from_repository
'''
Creates a `SourceCodeDataset` from a repository.
'''

create_decompiled_dataset = DecompiledCodeDataset.from_repository
'''
Creates a `DecompiledCodeDataset` from a repository.
'''


@utils.benchmark_function('Compiling dataset')
def compile_dataset(path: utils.PathLike, bins: Sequence[utils.PathLike], build_command: utils.Command,
                    manage_config: ManageConfig = ManageConfig(),
                    extract_config: ExtractConfig = ExtractConfig(),
                    dataset_config: DecompiledCodeDatasetConfig = DecompiledCodeDatasetConfig(),
                    generation_mode: DatasetGenerationMode = 'temp',
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
        generation_mode: Specifies the mode for generating the dataset.

    Returns:
        The generated dataset containing mappings of decompiled functions to their potential source code functions.
'''
    if generation_mode == 'temp-append':
        raise NotImplementedError('The temp-append generation mode is not implemented yet.')
    def try_transform_metadata(decompiled_function: DecompiledFunction,
                               source_functions: SourceCodeDataset,
                               other_dataset: DecompiledCodeDataset) -> Tuple[DecompiledFunction, SourceCodeDataset]:
        # Try to add transformed metadata to the decompiled function if it's in the other dataset
        matched_decompiled_function, matched_source_functions = \
            other_dataset.get(decompiled_function,
                              default=(None, None))
        if matched_decompiled_function and matched_source_functions:
            decompiled_function.add_metadata({
                'transformed_assembly': matched_decompiled_function.assembly,
                'transformed_decompiled_definition': matched_decompiled_function.definition
            })
            for source_function in matched_source_functions.values():
                source_function.add_metadata({
                    'transformed_source_definitions': source_function.definition,
                    'transformed_class_names': source_function.class_name
                })
            source_functions = \
                SourceCodeDataset(matched_source_functions.values())
        return decompiled_function, source_functions
    bins = [bins] if isinstance(bins, str) else bins
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
            # Rebase paths to commands and binaries if a temporary directory was created
            dataset_path = modified_source_dataset.get_common_directory()
            if dataset_path != path:
                logger.debug(f'Dataset is saved at {dataset_path}, but original repository path '
                             f'is {path}. Rebasing paths to binaries...')
                os.environ[REBASED_DIR_ENVIRON_KEY] = str(dataset_path)
                rebased_bins = [dataset_path /
                                Path(b).relative_to(path) for b in bins]
                rebased_bins_str = ', '.join(str(b) for b in rebased_bins)
                original_bins_str = ', '.join(str(b) for b in bins)
                logger.debug(f'Original binaries: {original_bins_str} ; '
                             f'Rebased binaries: {rebased_bins_str}')
            else:
                rebased_bins = bins
            # Compile repository
            with manage(build_command, dataset_path, config=manage_config):
                modified_decompiled_dataset = DecompiledCodeDataset.from_source_code_dataset(modified_source_dataset, rebased_bins,
                                                                                             config=dataset_config)
                if generation_mode == 'temp' or generation_mode == 'path':
                    logger.debug('Removing backup modified source dataset '
                                 f'"{modified_source_dataset_file.name}"')
                    Path(modified_source_dataset_file.name).unlink(
                        missing_ok=True)
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
                                                          generation_mode='path')
            return DecompiledCodeDataset(try_transform_metadata(d, s, modified_decompiled_dataset)
                                         for d, s in original_decompiled_dataset.values())
    else:
        with manage(build_command, path, config=manage_config):
            return create_decompiled_dataset(path, bins, extract_config=extract_config,
                                             dataset_config=dataset_config)
