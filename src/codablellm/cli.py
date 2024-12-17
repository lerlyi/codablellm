import json
import logging

from click import BadParameter
from codablellm import __version__
from codablellm.core import decompiler as codablellm_decompiler, utils
from codablellm.core import downloader
from codablellm.core import extractor as codablellm_extractor
from codablellm.dataset import DecompiledCodeDataset, SourceCodeDataset
from enum import Enum
from pathlib import Path
from rich import print
from typer import Argument, Exit, Option, Typer
from typing import Dict, Final, List, Optional, Tuple

from codablellm.decompilers.ghidra import Ghidra

logger = logging.getLogger('codablellm')

app = Typer()


class ExtractorOperation(str, Enum):
    PREPEND = 'prepend'
    APPEND = 'append'
    SET = 'set'

# Argument/option validation callbacks


def validate_dataset_format(path: Path) -> Path:
    if path.suffix.casefold() not in [e.casefold() for e in ['.json', '.jsonl', '.csv', '.tsv',
                                                             '.xlsx', '.xls', '.xlsm', '.md',
                                                             '.markdown', '.tex', '.html',
                                                             '.html', '.xml']]:
        raise BadParameter(f'Unsupported dataset format: "{path.suffix}"')
    return path

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
        print(f'[b]codablellm {__version__}')
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
DECOMPILE: Final[bool] = Option(False, '--decompile / --source', '-d / -s',
                                help='If the language supports decompiled code mapping, use '
                                '--decompiler to decompile the binaries specified by the bins '
                                'argument and add decompiled code to the dataset.')
DECOMPILER: Final[Optional[Tuple[str, str]]] = Option((codablellm_decompiler.DECOMPILER['name'],
                                                       codablellm_decompiler.DECOMPILER['class_path']
                                                       ),
                                                      help='Decompiler to use.',
                                                      metavar='<TEXT TEXT>')
DEBUG: Final[bool] = Option(False, '--debug', callback=toggle_debug_logging,
                            hidden=True)
EXTRACTORS_ARG: Final[Optional[Tuple[ExtractorOperation, Path]]] = Option(None, dir_okay=False, exists=True,
                                                                          metavar='<[prepend|append|set] FILE>',
                                                                          help='Order of extractors '
                                                                          'to use, including custom ones.')
GHIDRA: Final[Optional[Path]] = Option(Ghidra.get_path(), envvar=Ghidra.ENVIRON_KEY, dir_okay=False,
                                       callback=Ghidra.set_path,
                                       help="Path to Ghidra's analyzeHeadless command.")
GIT: Final[bool] = Option(False, '--git / --archive', help='Determines whether --url is a Git '
                          'download URL or a tarball/zipfile download URL.')
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
URL: Final[str] = Option('', help='Download a remote repository and save at the local path '
                         'specified by the REPO argument.')


@app.command()
def command(repo: Path = REPO, save_as: Path = SAVE_AS, bins: Optional[List[Path]] = BINS,
            accurate: bool = ACCURATE,
            debug: bool = DEBUG, decompile: bool = DECOMPILE,
            decompiler: Optional[Tuple[str, str]] = DECOMPILER,
            extractors: Optional[Tuple[ExtractorOperation,
                                       Path]] = EXTRACTORS_ARG,
            git: bool = GIT, ghidra: Optional[Path] = GHIDRA,
            max_decompiler_workers: Optional[int] = MAX_DECOMPILER_WORKERS,
            max_extractor_workers: Optional[int] = MAX_EXTRACTOR_WORKERS,
            url: str = URL, verbose: bool = VERBOSE, version: bool = VERSION) -> None:
    if url:
        # Download remote repository
        if git:
            downloader.clone(url, repo)
        else:
            downloader.decompress(url, repo)
    if decompiler:
        # Configure decompiler
        name, class_path = decompiler
        codablellm_decompiler.set_decompiler(name, class_path)
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
        if operation == ExtractorOperation.SET:
            codablellm_extractor.set_extractors(configured_extractors)
        else:
            for language, class_path in configured_extractors.items():
                order = 'last' if operation == ExtractorOperation.APPEND else 'first'
                codablellm_extractor.add_extractor(language, class_path,
                                                   order=order)
    # Create source code/decompiled code dataset
    if decompile:
        if not bins or not any(bins):
            raise BadParameter('Must specify at least one binary for decompiled code datasets.',
                               param_hint='bins')
        dataset = DecompiledCodeDataset.from_repository(repo, bins,
                                                        **utils.resolve_kwargs(max_decompiler_workers=max_decompiler_workers,
                                                                               max_extractor_workers=max_extractor_workers,
                                                                               accurate_progress=accurate))
    else:
        dataset = SourceCodeDataset.from_repository(repo,
                                                    **utils.resolve_kwargs(max_workers=max_extractor_workers,
                                                                           accurate_progress=accurate))
    # Save dataset
    dataset.save_as(save_as)
