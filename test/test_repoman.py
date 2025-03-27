from pathlib import Path
from subprocess import CalledProcessError
from pandas import DataFrame
import pytest

from codablellm.core.extractor import ExtractConfig
from codablellm.core.utils import Command
from codablellm.repoman import ManageConfig, compile_dataset, manage


def test_manage(failing_command: Command) -> None:
    with pytest.raises(CalledProcessError):
        with manage('make', 'path', ManageConfig(
            cleanup_command=failing_command,
            cleanup_error_handling='none'
        )):
            pass

@pytest.mark.skip(reason="Mock of decompiled functions is most likely causing the issue")
def test_compile_dataset(c_repository: Path, c_bin: Path) -> None:
    dataset = compile_dataset(c_repository, [c_bin], 'make',
                              extract_config=ExtractConfig(
                                  transform=lambda s: s.with_definition('',
                                                                        metadata={'is_empty': True})
    ),
        generation_mode='temp-append')
    mappings = dataset.values()
    assert dataset.to_df().to_dict() == DataFrame({'bin': [str(f.path) for f, _ in mappings],
                                                   'decompiled_uid': [f.uid for f, _ in mappings],
                                                   'decompiled_definition': [f.definition for f, _ in mappings],
                                                   'transformed_decompiled_definition': [f.metadata['transformed_decompiled_definition']
                                                                                         for f, _ in mappings],
                                                   'assembly': [f.assembly for f, _ in mappings],
                                                   'transformed_assembly': [f.metadata['transformed_assembly']
                                                                            for f, _ in mappings],
                                                   'architecture': [f.architecture for f, _ in mappings],
                                                   'source_files': [{uid: str(f.path) for uid, f in d.items()}
                                                                    for _, d in mappings],
                                                   'source_definitions': [{uid: f.definition for uid, f in d.items()}
                                                                          for _, d in mappings],
                                                   'transformed_source_definitions': [{uid: f.metadata['transformed_source_definitions']
                                                                                       for uid, f in d.items()}
                                                                                      for _, d in mappings],
                                                   'language': [{uid: f.language for uid, f in d.items()}
                                                                for _, d in mappings],
                                                   'name': [f.name for f, _ in mappings],
                                                   'source_file_start_bytes': [{uid: f.start_byte for uid, f in d.items()}
                                                                               for _, d in mappings],
                                                   'source_file_end_bytes': [{uid: f.end_byte for uid, f in d.items()}
                                                                             for _, d in mappings],
                                                   'class_names': [{uid: f.class_name for uid, f in d.items()}
                                                                   for _, d in mappings],
                                                   'transformed_class_names': [{uid: f.metadata['transformed_class_names']
                                                                                for uid, f in d.items()}
                                                                               for _, d in mappings],
                                                   'is_empty': [{uid: f.metadata['is_empty'] for uid, f in d.items()}
                                                                for _, d in mappings]}).set_index('decompiled_uid').to_dict()
