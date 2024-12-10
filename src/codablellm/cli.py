from codablellm.core import downloader
from pathlib import Path
from typer import Argument, Option, Typer
from typing import Final


app = Typer()

REPO: Final[Path] = Argument(help='Path to the local repository.', file_okay=False, exists=True,
                             show_default=False)
GIT: Final[bool] = Option(False, '--git / --archive', help='Determines whether --url is a Git '
                          'download URL or a tarball/zipfile download URL.')
URL: Final[str] = Option('', help='Download a remote repository and save at the local path '
                         'specified by the REPO argument.')


@app.command()
def command(repo: Path = REPO, git: bool = GIT, url: str = URL):
    if url:
        if git:
            downloader.clone(url, repo)
        else:
            downloader.decompress(url, repo)
