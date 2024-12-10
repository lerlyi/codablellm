from collections.abc import Mapping
from typing import Iterable, Sequence
from codablellm.core.function import CompiledFunction, Function
from codablellm.core.utils import PathLike
from pandas import DataFrame


class Dataset:

    def to_df(self) -> DataFrame:
        raise NotImplementedError()

    @classmethod
    def from_repository(cls, path: PathLike) -> 'Dataset':
        return cls()


class CompiledCodeDataset(Dataset, Mapping[CompiledFunction, Function]):

    @classmethod
    def from_compiliable_repository(cls, path: PathLike, bins: Sequence[PathLike]) -> 'CompiledCodeDataset':
        if len(bins) < 1:
            raise ValueError('Must at least specify one binary')
        return cls()
