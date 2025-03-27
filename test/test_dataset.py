from pathlib import Path

import pytest
from codablellm.core.extractor import ExtractConfig
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
                                                SourceCodeDatasetConfig(
                                                    generation_mode='path',
                                                    extract_config=ExtractConfig(
                                                        extract_as_repo=False
                                                    )
                                                ))
    temp_dataset = SourceCodeDataset.from_repository(c_repository)
    assert len(dataset) == 8
    assert len(temp_dataset) == 8
    assert dataset.get_common_directory() == c_repository
    assert temp_dataset.get_common_directory() == c_repository
    assert dataset.get('file1.c::function1') is not None
    functions = dataset.values()
    assert dataset.to_df().to_dict() == DataFrame({'path': [str(f.path) for f in functions],
                                                   'uid': [f.uid for f in functions],
                                                   'class_name': [f.class_name for f in functions],
                                                   'definition': [f.definition for f in functions],
                                                   'start_byte': [f.start_byte for f in functions],
                                                   'end_byte': [f.end_byte for f in functions],
                                                   'language': [f.language for f in functions],
                                                   'name': [f.name for f in functions]}).set_index('uid').to_dict()


def test_modified_source_dataset(c_repository: Path) -> None:
    dataset = SourceCodeDataset.from_repository(c_repository,
                                                SourceCodeDatasetConfig(
                                                    extract_config=ExtractConfig(
                                                        transform=lambda s: s.with_definition(
                                                            '', metadata={'custom_field': True})
                                                    )
                                                )
                                                )
    assert len(dataset) == 8
    functions = dataset.values()
    assert dataset.to_df().to_dict() == DataFrame({'path': [str(f.path) for f in functions],
                                                   'uid': [f.uid for f in functions],
                                                   'class_name': [f.class_name for f in functions],
                                                   'definition': [f.definition for f in functions],
                                                   'start_byte': [f.start_byte for f in functions],
                                                   'end_byte': [f.end_byte for f in functions],
                                                   'language': [f.language for f in functions],
                                                   'custom_field': [f.metadata['custom_field'] for f in functions],
                                                   'name': [f.name for f in functions]}).set_index('uid').to_dict()
    # dataset = SourceCodeDataset.from_repository(c_repository,
    #                                             SourceCodeDatasetConfig(
    #                                                 generation_mode='temp-append',
    #                                                 extract_config=ExtractConfig(
    #                                                     transform=lambda s: s.with_definition(
    #                                                         '', metadata={'custom_field': False})
    #                                                 )
    #                                             )
    #                                             )
    assert len(dataset) == 8


@pytest.mark.skip(reason='Test release-please workflow')
def test_decompiled_dataset(c_repository: Path, c_bin: Path) -> None:
    dataset = DecompiledCodeDataset.from_repository(c_repository, [c_bin])
    assert len(dataset) == 8
    mappings = dataset.values()
    assert dataset.to_df().to_dict() == DataFrame({'bin': [str(f.path) for f, _ in mappings],
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
