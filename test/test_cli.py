from typer.testing import CliRunner

from codablellm import __version__
from codablellm.cli import app

RUNNER = CliRunner()


def test_check_version() -> None:
    assert __version__ in RUNNER.invoke(app, '--version').stdout
