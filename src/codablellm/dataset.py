from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple, Union
from codablellm.core import decompiler
from codablellm.core import extractor
from codablellm.core import utils
from codablellm.core.function import CompiledFunction, SourceFunction, Subroutine
from pandas import DataFrame


class Dataset(ABC):

    @abstractmethod
    def to_df(self) -> DataFrame:
        pass


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
    def from_repository(cls, path: utils.PathLike,
                        languages: Optional[Sequence[extractor.Extractor]] = None) -> 'SourceCodeDataset':
        return cls(extractor.extract(path, **utils.resolve_kwargs(languages=languages)))


class CompiledCodeDataset(Dataset, Mapping[str, Tuple[CompiledFunction, SourceCodeDataset]]):

    def __init__(self,
                 mappings: Iterable[Tuple[CompiledFunction, SourceCodeDataset]]) -> None:
        super().__init__()
        self._mapping: Dict[str,
                            Tuple[CompiledFunction, SourceCodeDataset]
                            ] = {
                                m[0].uid: m for m in mappings
        }

    def __getitem__(self, key: Union[str, CompiledFunction]) -> Tuple[CompiledFunction, SourceCodeDataset]:
        if isinstance(key, CompiledFunction):
            return self[key.uid]
        return self._mapping[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._mapping)

    def __len__(self) -> int:
        return len(self._mapping)

    def to_df(self) -> DataFrame:
        return DataFrame.from_dict(self._mapping)

    def lookup(self, key: Union[str, SourceFunction]) -> List[Tuple[CompiledFunction, SourceCodeDataset]]:
        return [m for m in self.values() if key in m[1]]

    def to_source_code_dataset(self) -> SourceCodeDataset:
        return SourceCodeDataset(f for _, d in self.values() for f in d.values())

    @classmethod
    def from_repository(cls, path: utils.PathLike, bins: Sequence[utils.PathLike],
                        languages: Optional[Sequence[extractor.Extractor]] = None) -> 'CompiledCodeDataset':

        def get_potential_key(subroutine: Subroutine) -> str:
            return subroutine.uid.rsplit(':', maxsplit=1)[1].rsplit('.', maxsplit=1)[1]

        if not any(bins):
            raise ValueError('Must at least specify one binary')
        compiled_functions = [f for b in bins for f in decompiler.decompile(b)]
        source_dataset = SourceCodeDataset.from_repository(path,
                                                           **utils.resolve_kwargs(languages=languages))
        potential_mappings: Dict[str, List[SourceFunction]] = {}
        for source_function in source_dataset.values():
            potential_mappings.setdefault(get_potential_key(source_function),
                                          []).append(source_dataset[source_function.uid])
        return cls([(c, SourceCodeDataset(potential_mappings[get_potential_key(c)]))
                    for c in compiled_functions if get_potential_key(c) in potential_mappings])
