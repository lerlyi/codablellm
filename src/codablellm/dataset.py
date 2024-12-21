from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Mapping
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from typing import (
    Callable, Deque, Dict, Iterable, Iterator, List, Literal,
    Optional, Sequence, Tuple, Union)

from pandas import DataFrame

from codablellm.core import decompiler, extractor, utils
from codablellm.core.dashboard import ProcessPoolProgress
from codablellm.core.function import DecompiledFunction, SourceFunction, Function


class Dataset(ABC):

    @abstractmethod
    def to_df(self) -> DataFrame:
        pass

    def save_as(self, path: utils.PathLike) -> None:
        path = Path(path)
        extension = path.suffix.casefold()
        if extension in [e.casefold() for e in ['.json', '.jsonl']]:
            self.to_df().to_json(path, lines=extension == '.jsonl'.casefold())
        elif extension in [e.casefold() for e in ['.csv', '.tsv']]:
            self.to_df().to_csv(sep=',' if extension == '.csv'.casefold() else '\t')
        elif extension in [e.casefold() for e in ['.xlsx', '.xls', '.xlsm']]:
            self.to_df().to_excel(path)
        elif extension in [e.casefold() for e in ['.md', '.markdown']]:
            self.to_df().to_markdown(path)
        elif extension == '.tex'.casefold():
            self.to_df().to_latex(path)
        elif extension in [e.casefold() for e in ['.html', '.htm']]:
            self.to_df().to_html(path)
        elif extension == '.xml'.casefold():
            self.to_df().to_xml(path)
        else:
            raise ValueError(f'Unsupported file extension: {path.suffix}')


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

    @classmethod
    def from_repository(cls, path: utils.PathLike, max_workers: Optional[int] = None,
                        accurate_progress: Optional[bool] = None,
                        transform: Optional[Callable[[SourceFunction],
                                                     SourceFunction]] = None,
                        transform_mode: Literal['replace', 'append'] = 'append') -> 'SourceCodeDataset':
        if not transform or transform_mode == 'replace':
            return cls(extractor.extract(path,
                                         **utils.resolve_kwargs(max_workers=max_workers,
                                                                accurate_progress=accurate_progress,
                                                                transform=transform)))
        original_extraction_pool = extractor.extract(path, as_callable_pool=True,
                                                     **utils.resolve_kwargs(max_workers=max_workers,
                                                                            accurate_progress=accurate_progress))
        original_extraction_results: Deque[SourceFunction] = deque()
        with TemporaryDirectory() as copied_repo_dir:
            shutil.copytree(path, copied_repo_dir)
            modified_extraction_pool = extractor.extract(path, as_callable_pool=True,
                                                         **utils.resolve_kwargs(max_workers=max_workers,
                                                                                accurate_progress=accurate_progress))
            modified_extraction_results: Deque[SourceFunction] = deque()
            with ProcessPoolProgress.multi_progress((original_extraction_pool,  # type: ignore
                                                     original_extraction_results),
                                                    (modified_extraction_pool,  # type: ignore
                                                     modified_extraction_results)):
                return cls(s for d in [original_extraction_results, modified_extraction_results] for s in d)


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

        def get_potential_key(function: Function) -> str:
            return function.uid.rsplit(':', maxsplit=1)[1].rsplit('.', maxsplit=1)[1]

        potential_mappings: Dict[str, List[SourceFunction]] = {}
        for source_function in source_dataset.values():
            potential_mappings.setdefault(get_potential_key(source_function),
                                          []).append(source_dataset[source_function.uid])
        return cls([(d.to_stripped() if stripped else d, SourceCodeDataset(potential_mappings[get_potential_key(d)]))
                    for d in decompiled_functions if get_potential_key(d) in potential_mappings])

    @classmethod
    def from_repository(cls, path: utils.PathLike, bins: Sequence[utils.PathLike],
                        max_extractor_workers: Optional[int] = None,
                        max_decompiler_workers: Optional[int] = None,
                        accurate_progress: Optional[bool] = None,
                        stripped: bool = False) -> 'DecompiledCodeDataset':
        if not any(bins):
            raise ValueError('Must at least specify one binary')
        # Extract source code functions and decompile binaries in parallel
        original_extraction_pool = extractor.extract(path, as_callable_pool=True,
                                                     **utils.resolve_kwargs(max_workers=max_extractor_workers,
                                                                            accurate_progress=accurate_progress))
        source_functions: Deque[SourceFunction] = deque()
        decompile_pool = decompiler.decompile(bins, as_callable_pool=True,
                                              **utils.resolve_kwargs(max_workers=max_decompiler_workers))
        decompiled_functions: Deque[DecompiledFunction] = deque()
        with ProcessPoolProgress.multi_progress((original_extraction_pool,  # type: ignore
                                                 source_functions),
                                                (decompile_pool,  # type: ignore
                                                 decompiled_functions)):
            pass
        source_dataset = SourceCodeDataset(source_functions)
        return cls._from_dataset_and_decompiled(source_dataset, decompiled_functions, stripped)

    @classmethod
    def from_source_code_dataset(cls, dataset: SourceCodeDataset, bins: Sequence[utils.PathLike],
                                 max_workers: Optional[int] = None,
                                 stripped: bool = False) -> 'DecompiledCodeDataset':
        return cls._from_dataset_and_decompiled(dataset, decompiler.decompile(bins,
                                                                              **utils.resolve_kwargs(max_workers=max_workers)),
                                                stripped)
