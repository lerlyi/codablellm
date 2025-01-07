from pathlib import Path

import pytest
from codablellm.dataset import *


def test_save_dataset(tmp_path: Path) -> None:
    empty_dataset = SourceCodeDataset([])
    for ext in ['.json', '.jsonl', '.csv', '.tsv',
                '.xlsx', '.xls', '.xlsm', '.md',
                '.markdown', '.tex', '.html',
                '.html']:
        path = (tmp_path / 'dataset').with_suffix(ext)
        empty_dataset.save_as(path)
    with pytest.raises(ValueError):
        empty_dataset.save_as(tmp_path / 'dataset.unknown')


def test_source_dataset(c_repository: Path) -> None:
    dataset = SourceCodeDataset.from_repository(c_repository,
                                                generation_mode='path')
    temp_dataset = SourceCodeDataset.from_repository(c_repository)
    assert len(dataset) == 8
    assert len(temp_dataset) == 8
    assert dataset.get_common_path() == c_repository
    assert temp_dataset.get_common_path() == c_repository
    assert dataset.get('file1.c::function1') is not None


def test_modified_source_dataset(c_repository: Path) -> None:
    dataset = SourceCodeDataset.from_repository(c_repository,
                                                transform=lambda s: s.with_definition(''))
    assert len(dataset) == 8


def test_decompiled_dataset(c_repository: Path, c_bin: Path) -> None:
    dataset = DecompiledCodeDataset.from_repository(c_repository, [c_bin])
    assert len(dataset) == 0
