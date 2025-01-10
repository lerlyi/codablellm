from abc import ABC, abstractmethod
from collections.abc import Mapping
from contextlib import nullcontext
from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from typing import (Callable, Dict, Iterable, Iterator, List, Literal,
                    Optional, Sequence, Tuple, Union)

from pandas import DataFrame

from codablellm.core import decompiler, extractor, utils
from codablellm.core.dashboard import ProcessPoolProgress
from codablellm.core.function import DecompiledFunction, SourceFunction

logger = logging.getLogger('codablellm')


class Dataset(ABC):

    @abstractmethod
    def to_df(self) -> DataFrame:
        pass

    def save_as(self, path: utils.PathLike) -> None:

        @utils.requires_extra('excel', 'Excel exports', 'openpyxl')
        def to_excel(df: DataFrame, path: Path) -> None:
            df.to_excel(path)

        @utils.requires_extra('xml', 'XML exports', 'lxml')
        def to_xml(df: DataFrame, path: Path) -> None:
            df.to_xml(path)

        @utils.requires_extra('markdown', 'Markdown exports', 'tabulate')
        def to_markdown(df: DataFrame, path: Path) -> None:
            df.to_markdown(path)

        path = Path(path)
        extension = path.suffix.casefold()
        if extension in [e.casefold() for e in ['.json', '.jsonl']]:
            self.to_df().to_json(path, lines=extension == '.jsonl'.casefold(), orient='records')
        elif extension in [e.casefold() for e in ['.csv', '.tsv']]:
            self.to_df().to_csv(sep=',' if extension == '.csv'.casefold() else '\t')
        elif extension in [e.casefold() for e in ['.xlsx', '.xls', '.xlsm']]:
            to_excel(self.to_df(), path)
        elif extension in [e.casefold() for e in ['.md', '.markdown']]:
            to_markdown(self.to_df(), path)
        elif extension == '.tex'.casefold():
            self.to_df().to_latex(path)
        elif extension in [e.casefold() for e in ['.html', '.htm']]:
            self.to_df().to_html(path)
        elif extension == '.xml'.casefold():
            to_xml(self.to_df(), path)
        else:
            raise ValueError(f'Unsupported file extension: {path.suffix}')
        logger.info(f'Successfully saved {path.name}')


@dataclass
class SourceCodeDatasetConfig:
    generation_mode: Literal['path', 'temp', 'temp-append'] = 'temp'
    delete_temp: bool = True
    extract_config: extractor.ExtractConfig = \
        field(default_factory=extractor.ExtractConfig)
    log_generation_warning: bool = True

    def __post_init__(self) -> None:
        if (self.generation_mode == 'temp' or self.generation_mode == 'temp-append') and \
                not self.extract_config.transform:
            if self.log_generation_warning:
                logger.warning(f'Generation mode was specified as "{self.generation_mode}", but no '
                               'transform was provided. Changing generation mode to "path" to '
                               'save resources')
            self.generation_mode = 'path'


class SourceCodeDataset(Dataset, Mapping[str, SourceFunction]):

    def __init__(self, functions: Iterable[SourceFunction]) -> None:
        super().__init__()
        self._mapping: Dict[str, SourceFunction] = {
            f.uid: f for f in functions
        }

    def __getitem__(self, key: Union[str, SourceFunction]) -> SourceFunction:
        if isinstance(key, SourceFunction):
            return self[key.uid]
        return self._mapping[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._mapping)

    def __len__(self) -> int:
        return len(self._mapping)

    def to_df(self) -> DataFrame:
        return DataFrame.from_dict(self._mapping)

    def get_common_path(self) -> Path:
        return Path(os.path.commonpath(f.path for f in self.values()))

    @classmethod
    def from_repository(cls, path: utils.PathLike,
                        config: SourceCodeDatasetConfig = SourceCodeDatasetConfig(log_generation_warning=False)) -> 'SourceCodeDataset':
        if not config.extract_config.transform or config.generation_mode != 'temp-append':
            ctx = TemporaryDirectory(delete=config.delete_temp) if config.generation_mode == 'temp' and config.extract_config.transform \
                else nullcontext()
            with ctx as copied_repo_dir:
                if copied_repo_dir:
                    shutil.copytree(path, Path(
                        copied_repo_dir) / Path(path).name)
                    path = copied_repo_dir
                return cls(extractor.extract(path, config=config.extract_config))
        original_extraction_pool = extractor.extract(path, as_callable_pool=True,
                                                     config=config.extract_config)
        with TemporaryDirectory(delete=config.delete_temp) as copied_repo_dir:
            shutil.copytree(path, Path(copied_repo_dir) / Path(path).name)
            modified_extraction_pool = extractor.extract(path, as_callable_pool=True,
                                                         config=config.extract_config)
            original_extraction_results, \
                modified_extraction_results = ProcessPoolProgress.multi_progress(original_extraction_pool,  # type: ignore
                                                                                 modified_extraction_pool)  # type: ignore
            return cls(s for d in [original_extraction_results, modified_extraction_results]
                       for s in d)


@dataclass(frozen=True)
class DecompiledCodeDatasetConfig:
    extract_config: extractor.ExtractConfig = \
        field(default_factory=extractor.ExtractConfig)
    decompiler_config: decompiler.DecompileConfig = \
        field(default_factory=decompiler.DecompileConfig)
    strip: bool = False


class DecompiledCodeDataset(Dataset, Mapping[str, Tuple[DecompiledFunction, SourceCodeDataset]]):

    def __init__(self,
                 mappings: Iterable[Tuple[DecompiledFunction, SourceCodeDataset]]) -> None:
        super().__init__()
        self._mapping: Dict[str,
                            Tuple[DecompiledFunction, SourceCodeDataset]
                            ] = {
                                m[0].uid: m for m in mappings
        }

    def __getitem__(self, key: Union[str, DecompiledFunction]) -> Tuple[DecompiledFunction, SourceCodeDataset]:
        if isinstance(key, DecompiledFunction):
            return self[key.uid]
        return self._mapping[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._mapping)

    def __len__(self) -> int:
        return len(self._mapping)

    def to_df(self) -> DataFrame:
        return DataFrame.from_dict(self._mapping)

    def lookup(self, key: Union[str, SourceFunction]) -> List[Tuple[DecompiledFunction, SourceCodeDataset]]:
        return [m for m in self.values() if key in m[1]]

    def to_source_code_dataset(self) -> SourceCodeDataset:
        return SourceCodeDataset(f for _, d in self.values() for f in d.values())

    def to_stripped_dataset(self) -> 'DecompiledCodeDataset':
        return DecompiledCodeDataset((d.to_stripped(), s) for d, s in self.values())

    @classmethod
    def _from_dataset_and_decompiled(cls, source_dataset: SourceCodeDataset,
                                     decompiled_functions: Iterable[DecompiledFunction],
                                     stripped: bool) -> 'DecompiledCodeDataset':
        potential_mappings: Dict[str, List[SourceFunction]] = {}
        for source_function in source_dataset.values():
            potential_mappings.setdefault(source_function.uid,
                                          []).append(source_dataset[source_function.uid])
        mappings: List[Tuple[DecompiledFunction, SourceCodeDataset]] = []
        for decompiled_function in decompiled_functions:
            uid = SourceFunction.create_uid(decompiled_function.path,
                                            decompiled_function.name)
            if uid in mappings:
                if stripped:
                    decompiled_function = decompiled_function.to_stripped()
                mappings.append((decompiled_function,
                                SourceCodeDataset(potential_mappings[uid])))
        return cls(mappings)

    @classmethod
    def from_repository(cls, path: utils.PathLike, bins: Sequence[utils.PathLike],
                        extract_config: extractor.ExtractConfig = extractor.ExtractConfig(),
                        dataset_config: DecompiledCodeDatasetConfig = DecompiledCodeDatasetConfig()) -> 'DecompiledCodeDataset':
        if not any(bins):
            raise ValueError('Must at least specify one binary')
        # Extract source code functions and decompile binaries in parallel
        original_extraction_pool = extractor.extract(path, as_callable_pool=True,
                                                     config=extract_config)
        decompile_pool = decompiler.decompile(bins, as_callable_pool=True,
                                              config=dataset_config.decompiler_config)
        source_functions, decompiled_functions = \
            ProcessPoolProgress.multi_progress(original_extraction_pool,  # type: ignore
                                               decompile_pool)  # type: ignore
        source_dataset = SourceCodeDataset(source_functions)
        return cls._from_dataset_and_decompiled(source_dataset, decompiled_functions, dataset_config.strip)

    @classmethod
    def from_source_code_dataset(cls, dataset: SourceCodeDataset, bins: Sequence[utils.PathLike],
                                 config: DecompiledCodeDatasetConfig = DecompiledCodeDatasetConfig()) -> 'DecompiledCodeDataset':
        return cls._from_dataset_and_decompiled(dataset, decompiler.decompile(bins,
                                                                              **utils.resolve_kwargs(max_workers=config.decompiler_config.max_workers)),
                                                config.strip)

    @classmethod
    def concat(cls, *datasets: 'DecompiledCodeDataset') -> 'DecompiledCodeDataset':
        return cls(m for d in datasets for m in d.values())
