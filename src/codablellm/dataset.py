from codablellm.core.utils import PathLike
from pandas import DataFrame

class Dataset:
    
    def to_df(self) -> DataFrame:
        raise NotImplementedError()
    
    @classmethod
    def from_repository(cls, path: PathLike) -> 'Dataset':
        return cls()