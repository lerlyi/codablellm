import json
import logging

from click import BadParameter
from codablellm import __version__
from codablellm.core import downloader
from codablellm.core import utils
from codablellm.core.extractor import EXTRACTORS
from codablellm.core.function import SourceFunction
from codablellm.dataset import CompiledCodeDataset, Dataset, SourceCodeDataset
from enum import Enum
from pathlib import Path
from rich import print
from typer import Argument, Exit, Option, Typer
from typing import Dict, Final, List, Optional, Tuple

logger = logging.getLogger('codablellm')

app = Typer()


class ExtractorOperation(str, Enum):
    PREPEND = 'prepend'
    APPEND = 'append'
    REWRITE = 'set'

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
DECOMPILE: Final[bool] = Option(False, '--decompile / --source', '-d / -s',
                                help='If the language supports decompiled code mapping, use '
                                '--decompiler to decompile the binaries specified by the BINS '
                                'argument and add decompiled code to the dataset.')
DECOMPILER: Final[Optional[Tuple[str, str]]] = Option(None, help='Decompiler to use.',
                                                      metavar='<TEXT TEXT>')
DEBUG: Final[bool] = Option(False, '--debug', callback=toggle_debug_logging,
                            hidden=True)
EXTRACTORS_ARG: Final[Optional[Tuple[ExtractorOperation, Path]]] = Option(None, dir_okay=False, exists=True,
                                                                          metavar='<[prepend|append|set] FILE>',
                                                                          help='Order of extractors '
                                                                          'to use, including custom ones.')
GIT: Final[bool] = Option(False, '--git / --archive', help='Determines whether --url is a Git '
                          'download URL or a tarball/zipfile download URL.')
VERBOSE: Final[bool] = Option(False, '--verbose', '-v',
                              callback=toggle_logging,
                              help='Display verbose logging information.')
VERSION: Final[bool] = Option(False, '--version', is_eager=True, callback=show_version,
                              help='Shows the installed version of codablellm and exit.')
URL: Final[str] = Option('', help='Download a remote repository and save at the local path '
                         'specified by the REPO argument.')


@app.command()
def command(repo: Path = REPO, save_as: Path = SAVE_AS, bins: Optional[List[Path]] = BINS,
            debug: bool = DEBUG, decompile: bool = DECOMPILE,
            decompiler: Optional[Tuple[str, str]] = DECOMPILER,
            extractors: Optional[Tuple[ExtractorOperation,
                                       Path]] = EXTRACTORS_ARG,
            git: bool = GIT, url: str = URL, verbose: bool = VERBOSE, version: bool = VERSION):
    if url:
        # Download remote repository
        if git:
            downloader.clone(url, repo)
        else:
            downloader.decompress(url, repo)
    if extractors:
        # Configure function extractors
        operation, config_file = extractors
        try:
            configured_extractors: Dict[str, str] = json.loads(
                Path.read_text(config_file)
            )
        except json.JSONDecodeError as e:
            raise BadParameter('Could not decode extractor configuration file.',
                               param_hint='--extractors') from e
        if operation == ExtractorOperation.REWRITE:
            EXTRACTORS.clear()
        for language, import_path in configured_extractors.items():
            EXTRACTORS[language] = import_path
            if operation != ExtractorOperation.REWRITE:
                EXTRACTORS.move_to_end(
                    language, last=operation == ExtractorOperation.APPEND
                )
    # Create source code/decompiled code dataset
    if decompile:
        if not bins or not any(bins):
            raise BadParameter('Must specify at least one binary for decompiled code datasets.',
                               param_hint='bins')
        df = CompiledCodeDataset.from_repository(repo, bins).to_df()
    else:
        df = SourceCodeDataset.from_repository(repo).to_df()
    # Save dataset based on file extension
    extension = save_as.suffix.casefold()
    if extension in [e.casefold() for e in ['.json', '.jsonl']]:
        df.to_json(save_as, lines=extension == '.jsonl'.casefold())
    elif extension in [e.casefold() for e in ['.csv', '.tsv']]:
        df.to_csv(sep=',' if extension == '.csv'.casefold() else '\t')
    elif extension in [e.casefold() for e in ['.xlsx', '.xls', '.xlsm']]:
        df.to_excel(save_as)
    elif extension in [e.casefold() for e in ['.md', '.markdown']]:
        df.to_markdown(save_as)
    elif extension == '.tex'.casefold():
        df.to_latex(save_as)
    elif extension in [e.casefold() for e in ['.html', '.htm']]:
        df.to_html(save_as)
    elif extension == '.xml'.casefold():
        df.to_xml(save_as)
    else:
        original_extension = save_as.suffix
        save_as = save_as.with_suffix('.csv')
        print(f'[yellow][b]Warning:[/b] Unsupported file extension "{original_extension}", '
              f'saving dataset as CSV file "{save_as.name}"')
        df.to_csv(save_as)
    print('[green]Successfully saved dataset')
