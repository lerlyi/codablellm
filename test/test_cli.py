from pathlib import Path
from pandas import DataFrame
import pandas
import pytest
from typer.testing import CliRunner

from codablellm import __version__
from codablellm.cli import app
from codablellm.dataset import DecompiledCodeDataset

RUNNER = CliRunner()


def test_check_version() -> None:
    assert __version__ in RUNNER.invoke(app, '--version').stdout

@pytest.mark.skip(reason="Mock of decompiled functions is most likely causing the issue")
def test_compile_dataset(c_repository: Path, c_bin: Path, tmpdir: Path) -> None:
    out_file = tmpdir / 'out.csv'
    RUNNER.invoke(app, [str(c_repository), str(
        out_file), str(c_bin), '--build', 'make'])
    mappings = DecompiledCodeDataset.from_repository(
        c_repository, [c_bin]).values()
    assert pandas.read_csv(out_file).to_dict() == DataFrame({'bin': [str(f.path) for f, _ in mappings],
                                                             'decompiled_uid': [f.uid for f, _ in mappings],
                                                             'decompiled_definition': [f.definition for f, _ in mappings],
                                                             'assembly': [f.assembly for f, _ in mappings],
                                                             'architecture': [f.architecture for f, _ in mappings],
                                                             'source_files': [{uid: str(f.path) for uid, f in d.items()}
                                                                              for _, d in mappings],
                                                             'source_definitions': [{uid: f.definition for uid, f in d.items()}
                                                                                    for _, d in mappings],
                                                             'language': [{uid: f.language for uid, f in d.items()}
                                                                          for _, d in mappings],
                                                             'name': [f.name for f, _ in mappings],
                                                             'source_file_start_bytes': [{uid: f.start_byte for uid, f in d.items()}
                                                                                         for _, d in mappings],
                                                             'source_file_end_bytes': [{uid: f.end_byte for uid, f in d.items()}
                                                                                       for _, d in mappings],
                                                             'class_names': [{uid: f.class_name for uid, f in d.items()}
                                                                             for _, d in mappings]}).set_index('decompiled_uid').to_dict()
