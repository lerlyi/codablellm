from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Mapping
from concurrent.futures import Future, ProcessPoolExecutor
from pathlib import Path
from typing import Deque, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple, Union
from codablellm.core import decompiler
from codablellm.core import extractor
from codablellm.core import utils
from codablellm.core.function import DecompiledFunction, SourceFunction, Function
from pandas import DataFrame

from codablellm.core.dashboard import ProcessPoolProgress, Progress, PoolHandler, PoolHandlerArg


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
                        accurate_progress: Optional[bool] = None) -> 'SourceCodeDataset':
        return cls(extractor.extract(path), **utils.resolve_kwargs(max_workers=max_workers,
                                                                   accurate_progress=accurate_progress))


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

    @classmethod
    def from_repository(cls, path: utils.PathLike, bins: Sequence[utils.PathLike],
                        max_extractor_workers: Optional[int] = None,
                        max_decompiler_workers: Optional[int] = None,
                        accurate_progress: Optional[bool] = None) -> 'DecompiledCodeDataset':

        def get_potential_key(function: Function) -> str:
            return function.uid.rsplit(':', maxsplit=1)[1].rsplit('.', maxsplit=1)[1]

        if not any(bins):
            raise ValueError('Must at least specify one binary')
        # Extract source code functions and decompile binaries in parallel
        extract_handler: PoolHandler[str, Sequence[SourceFunction],
                                     List[SourceFunction]] = PoolHandler(
            extractor.extract(path, as_handler_arg=True,
                              # type: ignore
                              **utils.resolve_kwargs(max_workers=max_extractor_workers,
                                                     accurate_progress=accurate_progress))
        )
        source_functions: Deque[SourceFunction] = deque()
        decompile_handler: PoolHandler[utils.PathLike, Sequence[DecompiledFunction],
                                       List[DecompiledFunction]] = PoolHandler(
            decompiler.decompile(path, as_handler_arg=True,
                                 # type: ignore
                                 **utils.resolve_kwargs(max_workers=max_decompiler_workers))
        )
        decompiled_functions: Deque[DecompiledFunction] = deque()
        with ProcessPoolProgress.multi_progress((extract_handler, source_functions),
                                                (decompile_handler, decompiled_functions)):
            pass
        source_dataset = SourceCodeDataset(source_functions)
        # Create mappings of potential source code functions to be matched
        potential_mappings: Dict[str, List[SourceFunction]] = {}
        for source_function in source_dataset.values():
            potential_mappings.setdefault(get_potential_key(source_function),
                                          []).append(source_dataset[source_function.uid])
        return cls([(d, SourceCodeDataset(potential_mappings[get_potential_key(d)]))
                    for d in decompiled_functions if get_potential_key(d) in potential_mappings])
