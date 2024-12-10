import json

from click import BadParameter
from codablellm.core import downloader
from codablellm.core import utils
from codablellm.core.extractor import EXTRACTORS
from codablellm.dataset import Dataset
from enum import Enum
from pathlib import Path
from rich import print
from typer import Argument, Option, Typer
from typing import Dict, Final, List, Optional, Tuple


app = Typer()


class ExtractorOperation(str, Enum):
    PREPEND = 'prepend'
    APPEND = 'append'
    REWRITE = 'rewrite'

# Validation functions


def validate_binaries(paths: List[Path]) -> List[Path]:
    bins = []
    for path in paths:
        if path.is_dir():
            # Collect binaries from directory path
            bins.extend(f for f in path.glob('*') if utils.is_binary(f))
        # Ensure file is binary
        elif utils.is_binary(path):
            bins.append(path)
        else:
            raise BadParameter(f'"{path.name}" is not a binary.')
    # Ensure there is at least one binary
    if len(bins) < 1:
        raise BadParameter('Directories do not contain any binaries.')
    return bins


def validate_dataset_format(path: Path) -> Path:
    if path.suffix.casefold() not in [e.casefold() for e in ['.json', '.jsonl', '.csv', '.tsv',
                                                             '.xlsx', '.xls', '.xlsm', '.md',
                                                             '.markdown', '.tex', '.html',
                                                             '.html', '.xml']]:
        raise BadParameter(f'Unsupported dataset format: "{path.suffix}"')
    return path


# Arguments
REPO: Final[Path] = Argument(help='Path to the local repository.', file_okay=False, exists=True,
                             show_default=False)
SAVE_AS: Final[Path] = Argument(help='Path to save the dataset at.', dir_okay=False,
                                show_default=False, callback=validate_dataset_format)
BINS: Final[Optional[List[Path]]] = Argument(None, help='List of files or a directories '
                                             "containing the repository's compiled binaries.",
                                             metavar='[PATH]...', show_default=False,
                                             callback=validate_binaries)

# Options
DECOMPILER: Final[Optional[Tuple[str, str]]] = Option(None, help='Decompiler to use.',
                                                      metavar='<TEXT TEXT>')
EXTRACTORS_ARG: Final[Optional[Tuple[ExtractorOperation, Path]]] = Option(None, help='Order of extractors '
                                                                          'to use, including custom ones.',
                                                                          dir_okay=False, exists=True,
                                                                          metavar='<[prepend|append|rewrite] FILE>')
GIT: Final[bool] = Option(False, '--git / --archive', help='Determines whether --url is a Git '
                          'download URL or a tarball/zipfile download URL.')
URL: Final[str] = Option('', help='Download a remote repository and save at the local path '
                         'specified by the REPO argument.')


@app.command()
def command(repo: Path = REPO, save_as: Path = SAVE_AS, bins: Optional[List[Path]] = BINS,
            decompiler: Optional[Tuple[str, str]] = DECOMPILER,
            extractors: Optional[Tuple[ExtractorOperation,
                                       Path]] = EXTRACTORS_ARG,
            git: bool = GIT, url: str = URL):
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
    # Save dataset based on file extension
    df = Dataset.from_repository(repo).to_df()
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
