'''
The codablellm command line interface.
'''

from enum import Enum
import importlib
import json
from pathlib import Path
import logging
import os
import sys

from click import BadParameter
from rich import print
from rich.prompt import Confirm
from typer import Argument, Exit, Option, Typer
from typing import Any, Dict, Final, List, Optional, Tuple

import codablellm
from codablellm.core import downloader
from codablellm.core.decompiler import DecompileConfig
from codablellm.core.extractor import ExtractConfig, Transform
from codablellm.dataset import DecompiledCodeDatasetConfig, Mapper, SourceCodeDatasetConfig
from codablellm.decompilers.ghidra import Ghidra
from codablellm.repoman import ManageConfig

logger = logging.getLogger('codablellm')

app = Typer()

# Argument/option choices


class ExtractorConfigOperation(str, Enum):
    PREPEND = 'prepend'
    APPEND = 'append'
    SET = 'set'


class GenerationMode(str, Enum):
    PATH = 'path'
    TEMP = 'temp'
#    TEMP_APPEND = 'temp-append'


class CommandErrorHandler(str, Enum):
    INTERACTIVE = 'interactive'
    IGNORE = 'ignore'
    NONE = 'none'


class RunFrom(str, Enum):
    CWD = 'cwd'
    REPO = 'repo'

# Default configurations


DEFAULT_SOURCE_CODE_DATASET_CONFIG: Final[SourceCodeDatasetConfig] = \
    SourceCodeDatasetConfig(log_generation_warning=False)
DEFAULT_DECOMPILED_CODE_DATASET_CONFIG: Final[DecompiledCodeDatasetConfig] = \
    DecompiledCodeDatasetConfig()
DEFAULT_MANAGE_CONFIG: Final[ManageConfig] = ManageConfig()

# Argument/option validation callbacks


def validate_dataset_format(path: Path) -> Path:
    if path.suffix.casefold() not in [e.casefold() for e in ['.json', '.jsonl', '.csv', '.tsv',
                                                             '.xlsx', '.xls', '.xlsm', '.md',
                                                             '.markdown', '.tex', '.html',
                                                             '.html', '.xml']]:
        raise BadParameter(f'Unsupported dataset format: "{path.suffix}"')
    return path

# Argument/option parsers


def dynamic_import(path: str) -> Any:
    if '/' in path:
        file_delimeter = '/'
    elif '\\' in path:
        file_delimeter = '\\'
    else:
        file_delimeter = None
    if file_delimeter:
        parent_str_dir, path = path.rsplit(file_delimeter, maxsplit=1)
        parent_dir = Path(parent_str_dir).resolve()
    else:
        parent_dir = Path(os.getcwd())
    # Add parent directory to sys.path to allow for dynamic imports of extractors and mappers
    sys.path.insert(0, str(parent_dir))
    module_path, callable_name = path.rsplit('.', 1)
    try:
        module = importlib.import_module(module_path)
        return getattr(module, callable_name)
    except (ModuleNotFoundError, AttributeError) as e:
        raise BadParameter(f'Cannot find "{path}"') from e


def parse_transform(callable_path: str) -> Transform:
    return dynamic_import(callable_path)


def parse_mapper(callable_path: str) -> Mapper:
    return dynamic_import(callable_path)

# Miscellaneous argument/option callbacks


def toggle_logging(enable: bool) -> None:
    if enable and logger.level == logging.NOTSET:
        logger.setLevel(logging.INFO)
    elif logger.level != logging.DEBUG:
        logging.disable()


def toggle_debug_logging(enable: bool) -> None:
    if enable:
        logger.setLevel(logging.DEBUG)


def show_version(show: bool) -> None:
    if show:
        print(f'[b]codablellm {codablellm.__version__}')
        raise Exit()


def try_create_repo_dir(path: Path) -> Path:
    Path(path).mkdir(parents=True, exist_ok=True)
    return path


# Arguments
REPO: Final[Path] = Argument(file_okay=False, show_default=False,
                             callback=try_create_repo_dir,
                             help='Path to the local repository.')
SAVE_AS: Final[Path] = Argument(dir_okay=False, show_default=False,
                                callback=validate_dataset_format,
                                help='Path to save the dataset at.')
BINS: Final[Optional[List[Path]]] = Argument(None, metavar='[PATH]...', show_default=False,
                                             help='List of files or a directories containing the '
                                             "repository's compiled binaries.")

# Options
ACCURATE: Final[bool] = Option(DEFAULT_SOURCE_CODE_DATASET_CONFIG.extract_config.accurate_progress,
                               '--accurate / --lazy',
                               help='Displays estimated time remaining and detailed '
                               'progress reporting of source function extraction '
                               'if --accurate is enabled, at a cost of more '
                               'memory usage and a longer startup time to collect '
                               'the sequence of source code files.')
BUILD: Final[Optional[str]] = Option(None, '--build', '-b', metavar='COMMAND',
                                     help='If --decompile is specified, the repository will be '
                                     'built using the value of this option as the build command.')
CHECKPOINT: Final[int] = Option(DEFAULT_SOURCE_CODE_DATASET_CONFIG.extract_config.checkpoint,
                                min=0,
                                help='Number of extraction entries after which a backup dataset '
                                'file will be saved in case of a crash.')
CLEANUP: Final[Optional[str]] = Option(DEFAULT_MANAGE_CONFIG.cleanup_command,
                                       '--cleanup', '-c', metavar='COMMAND',
                                       help='If --decompile is specified, the repository will be '
                                       'cleaned up after the dataset is created, using the value of '
                                       'this option as the build command.')
DECOMPILE: Final[bool] = Option(False, '--decompile / --source', '-d / -s',
                                help='If the language supports decompiled code mapping, use '
                                '--decompiler to decompile the binaries specified by the bins '
                                'argument and add decompiled code to the dataset.')
DECOMPILER: Final[str] = Option(codablellm.decompiler.DECOMPILER['class_path'],
                                help='Decompiler to use.',
                                metavar='CLASSPATH')
DEBUG: Final[bool] = Option(False, '--debug', callback=toggle_debug_logging,
                            hidden=True)
EXCLUDE_SUBPATH: Final[Optional[List[Path]]] = Option(list(DEFAULT_SOURCE_CODE_DATASET_CONFIG.extract_config.exclude_subpaths),
                                                      '--exclude-subpath', '-e',
                                                      help='Path relative to the repository '
                                                      'directory to exclude from the dataset '
                                                      'generation.')
EXCLUSIVE_SUBPATH: Final[Optional[List[Path]]] = Option(list(DEFAULT_SOURCE_CODE_DATASET_CONFIG.extract_config.exclusive_subpaths),
                                                        '--exclusive-subpath', '-E',
                                                        help='Path relative to the repository '
                                                        'directory to exclusively include in the dataset '
                                                        'generation.')
EXTRACTORS: Final[Optional[Tuple[ExtractorConfigOperation, Path]]] = Option(None, dir_okay=False, exists=True,
                                                                            metavar='<[prepend|append|set] FILE>',
                                                                            help='Order of extractors '
                                                                            'to use, including custom ones.')
GENERATION_MODE: Final[GenerationMode] = Option(DEFAULT_SOURCE_CODE_DATASET_CONFIG.generation_mode,
                                                help='Specify how the dataset should be '
                                                'generated from the repository.')
GHIDRA: Final[Optional[Path]] = Option(Ghidra.get_path(), envvar=Ghidra.ENVIRON_KEY, dir_okay=False,
                                       callback=lambda v: Ghidra.set_path(
                                           v) if v else None,
                                       help="Path to Ghidra's analyzeHeadless command.")
GIT: Final[bool] = Option(False, '--git / --archive', help='Determines whether --url is a Git '
                          'download URL or a tarball/zipfile download URL.')
BUILD_ERROR_HANDLING: Final[CommandErrorHandler] = Option(DEFAULT_MANAGE_CONFIG.build_error_handling,
                                                          help='Specifies how to handle errors that occur '
                                                          'during the cleanup process. Options include '
                                                          'ignoring the error, raising an exception, or '
                                                          'prompting the user for manual intervention.')
CLEANUP_ERROR_HANDLING: Final[CommandErrorHandler] = Option(DEFAULT_MANAGE_CONFIG.cleanup_error_handling,
                                                            help='Specifies how to handle errors that occur '
                                                            'during the cleanup process. Options include '
                                                            'ignoring the error, raising an exception, or '
                                                            'prompting the user for manual intervention.')
MAPPER: Final[Mapper] = Option('codablellm.dataset.DEFAULT_MAPPER',
                               metavar='CALLABLEPATH',
                               help='Mapper to use for mapping decompiled functions to source '
                               'code functions.',
                               parser=parse_mapper)
MAX_DECOMPILER_WORKERS: Final[Optional[int]] = Option(DEFAULT_DECOMPILED_CODE_DATASET_CONFIG.decompiler_config.max_workers,
                                                      min=1,
                                                      help='Maximum number of workers to use to '
                                                      'decompile binaries in parallel.')
MAX_EXTRACTOR_WORKERS: Final[Optional[int]] = Option(DEFAULT_SOURCE_CODE_DATASET_CONFIG.extract_config.max_workers,
                                                     min=1,
                                                     help='Maximum number of workers to use to '
                                                     'extract source code functions in parallel.')
VERBOSE: Final[bool] = Option(False, '--verbose', '-v',
                              callback=toggle_logging,
                              help='Display verbose logging information.')
VERSION: Final[bool] = Option(False, '--version', is_eager=True, callback=show_version,
                              help='Shows the installed version of codablellm and exit.')
TRANSFORM: Final[Optional[codablellm.extractor.Transform]] = Option(DEFAULT_SOURCE_CODE_DATASET_CONFIG.extract_config.transform,
                                                                    '--transform', '-t',
                                                                    metavar='CALLABLEPATH',
                                                                    help='Transformation function to use '
                                                                    'when extracting source code '
                                                                    'functions.',
                                                                    parser=parse_transform)
RUN_FROM: Final[RunFrom] = Option(DEFAULT_MANAGE_CONFIG.run_from,
                                  help="Where to run build/clean commands from: 'repo' (the root "
                                  "of the repository, whether real or temp) or 'cwd' (your "
                                  'current shell directory). Useful for managing relative path behavior.')
STRIP: Final[bool] = Option(DEFAULT_DECOMPILED_CODE_DATASET_CONFIG.strip,
                            help='If a decompiled dataset is being created, strip the symbols '
                            'after decompiling')
USE_CHECKPOINT: Final[Optional[bool]] = Option(None, '--use-checkpoint / --ignore-checkpoint',
                                               show_default=False,
                                               help='Enable the use of an extraction checkpoint '
                                               'to resume from a previously saved state.')
URL: Final[str] = Option('', help='Download a remote repository and save at the local path '
                         'specified by the REPO argument.')


@app.command()
def command(repo: Path = REPO, save_as: Path = SAVE_AS, bins: Optional[List[Path]] = BINS,
            accurate: bool = ACCURATE, build: Optional[str] = BUILD,
            build_error_handling: CommandErrorHandler = BUILD_ERROR_HANDLING,
            cleanup: Optional[str] = CLEANUP,
            cleanup_error_handling: CommandErrorHandler = CLEANUP_ERROR_HANDLING,
            checkpoint: int = CHECKPOINT,
            debug: bool = DEBUG, decompile: bool = DECOMPILE,
            decompiler: str = DECOMPILER,
            exclude_subpath: Optional[List[Path]] = EXCLUDE_SUBPATH,
            exclusive_subpath: Optional[List[Path]] = EXCLUSIVE_SUBPATH,
            extractors: Optional[Tuple[ExtractorConfigOperation,
                                       Path]] = EXTRACTORS,
            generation_mode: GenerationMode = GENERATION_MODE,
            git: bool = GIT, ghidra: Optional[Path] = GHIDRA,
            mapper: Mapper = MAPPER,
            max_decompiler_workers: Optional[int] = MAX_DECOMPILER_WORKERS,
            max_extractor_workers: Optional[int] = MAX_EXTRACTOR_WORKERS,
            run_from: RunFrom = RUN_FROM,
            strip: bool = STRIP,
            transform: Optional[codablellm.extractor.Transform] = TRANSFORM,
            use_checkpoint: Optional[bool] = USE_CHECKPOINT,
            url: str = URL, verbose: bool = VERBOSE, version: bool = VERSION) -> None:
    '''
    Creates a code dataset from a local repository.
    '''
    # Configure decompiler
    codablellm.decompiler.set_decompiler(decompiler)
    if extractors:
        # Configure function extractors
        operation, config_file = extractors
        try:
            # Load JSON file containing extractors
            configured_extractors: Dict[str, str] = json.loads(
                Path.read_text(config_file)
            )
        except json.JSONDecodeError as e:
            raise BadParameter('Could not decode extractor configuration file.',
                               param_hint='--extractors') from e
        if operation == ExtractorConfigOperation.SET:
            codablellm.extractor.set_extractors(configured_extractors)
        else:
            for language, class_path in configured_extractors.items():
                order = 'last' if operation == ExtractorConfigOperation.APPEND else 'first'
                codablellm.extractor.add_extractor(language, class_path,
                                                   order=order)
    if url:
        # Download remote repository
        if git:
            downloader.clone(url, repo)
        else:
            downloader.decompress(url, repo)
    # Create the extractor configuration
    if use_checkpoint is None:
        if any(codablellm.extractor.get_checkpoint_files()):
            use_checkpoint = Confirm.ask(
                'Extraction checkpoint files detected. Would you like to resume from the most '
                'recent checkpoint?',
                case_sensitive=False
            )
        else:
            use_checkpoint = False
    extract_config = ExtractConfig(
        max_workers=max_extractor_workers,
        accurate_progress=accurate,
        transform=transform,
        exclusive_subpaths=set(
            exclusive_subpath) if exclusive_subpath else set(),
        exclude_subpaths=set(exclude_subpath) if exclude_subpath else set(),
        checkpoint=checkpoint,
        use_checkpoint=use_checkpoint
    )
    if build:
        logger.warning('--build specified without --decompile. --decompile enabled '
                       'automatically.')
        decompile = True
    # Create source code/decompiled code dataset
    if decompile:
        if not bins or not any(bins):
            raise BadParameter('Must specify at least one binary for decompiled code datasets.',
                               param_hint='bins')
        dataset_config = DecompiledCodeDatasetConfig(
            extract_config=extract_config,
            strip=strip,
            decompiler_config=DecompileConfig(
                max_workers=max_decompiler_workers
            ),
            mapper=mapper,
        )
        if not build:
            dataset = codablellm.create_decompiled_dataset(repo, bins,
                                                           extract_config=extract_config,
                                                           dataset_config=dataset_config)
        else:
            manage_config = ManageConfig(
                cleanup_command=cleanup,
                run_from=run_from,  # type: ignore
                build_error_handling=build_error_handling,  # type: ignore
                cleanup_error_handling=cleanup_error_handling)  # type: ignore
            dataset = codablellm.compile_dataset(repo, bins, build,
                                                 manage_config=manage_config,
                                                 extract_config=extract_config,
                                                 dataset_config=dataset_config,
                                                 generation_mode=generation_mode,  # type: ignore
                                                 )
    else:
        dataset_config = SourceCodeDatasetConfig(
            generation_mode=str(generation_mode),  # type: ignore
            extract_config=extract_config
        )
        dataset = codablellm.create_source_dataset(repo, config=dataset_config)
    # Save dataset
    dataset.save_as(save_as)
