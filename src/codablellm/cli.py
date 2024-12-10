from codablellm.core import downloader
from codablellm.dataset import Dataset
from pathlib import Path
from rich import print
from typer import Argument, Option, Typer
from typing import Final


app = Typer()

# Arguments
REPO: Final[Path] = Argument(help='Path to the local repository.', file_okay=False, exists=True,
                             show_default=False)
SAVE_AS: Final[Path] = Argument(help='Path to where the dataset at.', dir_okay=False,
                                show_default=False)

# Options
GIT: Final[bool] = Option(False, '--git / --archive', help='Determines whether --url is a Git '
                          'download URL or a tarball/zipfile download URL.')
URL: Final[str] = Option('', help='Download a remote repository and save at the local path '
                         'specified by the REPO argument.')


@app.command()
def command(repo: Path = REPO, save_as: Path = SAVE_AS, git: bool = GIT, url: str = URL):
    if url:
        if git:
            downloader.clone(url, repo)
        else:
            downloader.decompress(url, repo)
    df = Dataset.from_repository(repo).to_df()
    extension = save_as.suffix.casefold()
    # Save dataset based on file extension
    if extension in [e.casefold() for e in ['.json', '.jsonl']]:
        df.to_json(save_as, lines=extension == '.jsonl'.casefold())
    elif extension in [e.casefold() for e in ['.csv', '.tsv']]:
        df.to_csv(sep=',' if extension == '.csv'.casefold() else '\t')
    elif extension in [e.casefold() for e in ['.html', '.htm']]:
        df.to_html(save_as)
    elif extension in [e.casefold() for e in ['.xlsx', '.xls', '.xlsm']]:
        df.to_excel(save_as)
    elif extension in [e.casefold() for e in ['.md', '.markdown']]:
        df.to_markdown(save_as)
    elif extension == '.tex'.casefold():
        df.to_latex(save_as)
    elif extension == '.xml'.casefold():
        df.to_xml(save_as)
    else:
        original_extension = save_as.suffix
        save_as = save_as.with_suffix('.csv')
        print(f'[yellow][b]Warning:[/b] Unsupported file extension "{original_extension}", '
              f'saving dataset as CSV file "{save_as.name}"')
        df.to_csv(save_as)
    print('[green]Successfully saved dataset.')
