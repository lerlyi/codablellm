import importlib
import json
import logging

from click import BadParameter
from enum import Enum
from pathlib import Path
from rich import print
from typer import Argument, Exit, Option, Typer
from typing import Callable, Dict, Final, List, Optional, Tuple

import codablellm
from codablellm.core import downloader
from codablellm.core.function import SourceFunction
from codablellm.decompilers.ghidra import Ghidra

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
    TEMP_APPEND = 'temp-append'

# Argument/option validation callbacks


def validate_dataset_format(path: Path) -> Path:
    if path.suffix.casefold() not in [e.casefold() for e in ['.json', '.jsonl', '.csv', '.tsv',
                                                             '.xlsx', '.xls', '.xlsm', '.md',
                                                             '.markdown', '.tex', '.html',
                                                             '.html', '.xml']]:
        raise BadParameter(f'Unsupported dataset format: "{path.suffix}"')
    return path

# Argument/option parsers


def parse_transform(callable_path: str) -> Callable[[SourceFunction], SourceFunction]:
    module_path, callable_name = callable_path.rsplit('.', 1)
    try:
        module = importlib.import_module(module_path)
        return getattr(module, callable_name)
    except (ModuleNotFoundError, AttributeError) as e:
        raise BadParameter(f'Cannot find "{callable_path}"') from e

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


# Arguments
REPO: Final[Path] = Argument(file_okay=False, exists=True, show_default=False,
                             help='Path to the local repository.')
SAVE_AS: Final[Path] = Argument(dir_okay=False, show_default=False,
                                callback=validate_dataset_format,
                                help='Path to save the dataset at.')
BINS: Final[Optional[List[Path]]] = Argument(None, metavar='[PATH]...', show_default=False,
                                             help='List of files or a directories containing the '
                                             "repository's compiled binaries.")

# Options
ACCURATE: Final[bool] = Option(True, '--accurate / --lazy',
                               help='Displays estimated time remaining and detailed '
                               'progress reporting of source function extraction '
                               'if --accurate is enabled, at a cost of more '
                               'memory usage and a longer startup time to collect '
                               'the sequence of source code files.')
BUILD: Final[Optional[str]] = Option(None, '--build', '-b', metavar='COMMAND',
                                     help='If --decompile is specified, the repository will be '
                                     'built using the value of this option as the build command.')
CLEANUP: Final[Optional[str]] = Option(None, '--cleanup', '-c', metavar='COMMAND',
                                       help='If --decompile is specified, the repository will be '
                                       'cleaned up after the dataset is created, using the value of '
                                       'this option as the build command.')
DECOMPILE: Final[bool] = Option(False, '--decompile / --source', '-d / -s',
                                help='If the language supports decompiled code mapping, use '
                                '--decompiler to decompile the binaries specified by the bins '
                                'argument and add decompiled code to the dataset.')
DECOMPILER: Final[Optional[Tuple[str, str]]] = Option((codablellm.decompiler.DECOMPILER['name'],
                                                       codablellm.decompiler.DECOMPILER['class_path']
                                                       ),
                                                      help='Decompiler to use.',
                                                      metavar='<TEXT CLASSPATH>')
DEBUG: Final[bool] = Option(False, '--debug', callback=toggle_debug_logging,
                            hidden=True)
EXCLUDE_SUBPATH: Final[Optional[List[Path]]] = Option(None,
                                                      help='Path relative to the repository '
                                                      'directory to exclude from the dataset '
                                                      'generation.')
EXCLUSIVE_SUBPATH: Final[Optional[List[Path]]] = Option(None,
                                                        help='Path relative to the repository '
                                                        'directory to exclusively include in the dataset '
                                                        'generation.')
EXTRACTORS_ARG: Final[Optional[Tuple[ExtractorConfigOperation, Path]]] = Option(None, dir_okay=False, exists=True,
                                                                                metavar='<[prepend|append|set] FILE>',
                                                                                help='Order of extractors '
                                                                                'to use, including custom ones.')
GENERATION_MODE: Final[GenerationMode] = Option('temp',
                                                help='Specify how the dataset should be '
                                                'generated from the repository.')
GHIDRA: Final[Optional[Path]] = Option(Ghidra.get_path(), envvar=Ghidra.ENVIRON_KEY, dir_okay=False,
                                       callback=Ghidra.set_path,
                                       help="Path to Ghidra's analyzeHeadless command.")
GIT: Final[bool] = Option(False, '--git / --archive', help='Determines whether --url is a Git '
                          'download URL or a tarball/zipfile download URL.')
IGNORE_BUILD_ERRORS: Final[bool] = Option(False, '--ignore-build-errors',
                                          help='Does not exit if the build command specified with '
                                          '--build exits with a non-successful status.')
IGNORE_CLEANUP_ERRORS: Final[bool] = Option(False, '--ignore-cleanup-errors',
                                            help='Does not exit if the cleanup command specified '
                                            'with --cleanup exits with a non-successful status '
                                            '(dataset will still be saved).')
MAX_DECOMPILER_WORKERS: Final[Optional[int]] = Option(None, min=1,
                                                      help='Maximum number of workers to use to '
                                                      'decompile binaries in parallel.')
MAX_EXTRACTOR_WORKERS: Final[Optional[int]] = Option(None, min=1,
                                                     help='Maximum number of workers to use to '
                                                     'extract source code functions in parallel.')
VERBOSE: Final[bool] = Option(False, '--verbose', '-v',
                              callback=toggle_logging,
                              help='Display verbose logging information.')
VERSION: Final[bool] = Option(False, '--version', is_eager=True, callback=show_version,
                              help='Shows the installed version of codablellm and exit.')
TRANSFORM: Final[Optional[Callable[[SourceFunction],
                                   SourceFunction]]] = Option(None, '--transform', '-t',
                                                              metavar='CALLABLEPATH',
                                                              help='Transformation function to use '
                                                              'when extracting source code '
                                                              'functions.',
                                                              parser=parse_transform)
REPO_BUILD_ARG: Final[bool] = Option(False, '--repo-build-arg', '-B',
                                     help='Will append the build command with the path of the '
                                     "repository's path as the first argument for the command "
                                     'specified with --build. This may be useful '
                                     'when --generation-mode temp or '
                                     '--generation-mode temp-append is specified.')
REPO_CLEANUP_ARG: Final[bool] = Option(False, '--repo-cleanup-arg', '-C',
                                       help='Will append the cleanup command with the path of the '
                                       "repository's path as the first argument for the command "
                                       'specified with --cleanup. This may be useful '
                                       'when --generation-mode temp or '
                                       '--generation-mode temp-append is specified.')
URL: Final[str] = Option('', help='Download a remote repository and save at the local path '
                         'specified by the REPO argument.')


@app.command()
def command(repo: Path = REPO, save_as: Path = SAVE_AS, bins: Optional[List[Path]] = BINS,
            accurate: bool = ACCURATE, build: Optional[str] = BUILD,
            cleanup: Optional[str] = CLEANUP,
            debug: bool = DEBUG, decompile: bool = DECOMPILE,
            decompiler: Optional[Tuple[str, str]] = DECOMPILER,
            exclude_subpath: Optional[List[Path]] = EXCLUDE_SUBPATH,
            exclusive_subpath: Optional[List[Path]] = EXCLUSIVE_SUBPATH,
            extractors: Optional[Tuple[ExtractorConfigOperation,
                                       Path]] = EXTRACTORS_ARG,
            generation_mode: GenerationMode = GENERATION_MODE,
            git: bool = GIT, ghidra: Optional[Path] = GHIDRA,
            ignore_build_errors: bool = IGNORE_BUILD_ERRORS,
            ignore_cleanup_errors: bool = IGNORE_CLEANUP_ERRORS,
            max_decompiler_workers: Optional[int] = MAX_DECOMPILER_WORKERS,
            max_extractor_workers: Optional[int] = MAX_EXTRACTOR_WORKERS,
            repo_build_arg: bool = REPO_BUILD_ARG,
            repo_cleanup_arg: bool = REPO_CLEANUP_ARG,
            transform: Optional[Callable[[SourceFunction],
                                         SourceFunction]] = TRANSFORM,
            url: str = URL, verbose: bool = VERBOSE, version: bool = VERSION) -> None:
    if decompiler:
        # Configure decompiler
        name, class_path = decompiler
        codablellm.decompiler.set_decompiler(name, class_path)
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
    # Create source code/decompiled code dataset
    if decompile:
        if not bins or not any(bins):
            raise BadParameter('Must specify at least one binary for decompiled code datasets.',
                               param_hint='bins')
        if not build:
            dataset = codablellm.create_decompiled_dataset(repo, bins,
                                                           max_decompiler_workers=max_decompiler_workers,
                                                           max_extractor_workers=max_extractor_workers,
                                                           accurate_progress=accurate)
        else:
            if repo_build_arg or repo_cleanup_arg:
                if repo_build_arg and repo_cleanup_arg:
                    repo_arg_with = 'both'
                else:
                    repo_arg_with = 'build' if repo_build_arg else 'cleanup'
            else:
                repo_arg_with = None
            dataset = codablellm.compile_dataset(repo, bins, build, max_decompiler_workers=max_decompiler_workers,
                                                 max_extractor_workers=max_extractor_workers,
                                                 progress='accurate' if accurate else 'lazy',
                                                 transform=transform,
                                                 generation_mode=str(
                                                     generation_mode),  # type: ignore
                                                 cleanup_command=cleanup,
                                                 ignore_build_errors=ignore_build_errors,
                                                 ignore_cleanup_errors=ignore_cleanup_errors,
                                                 repo_arg_with=repo_arg_with)
    else:
        dataset = codablellm.create_source_dataset(repo,
                                                   generation_mode=str(
                                                       generation_mode),  # type: ignore
                                                   accurate_progress=accurate,
                                                   max_workers=max_extractor_workers,
                                                   transform=transform)
    # Save dataset
    dataset.save_as(save_as)
