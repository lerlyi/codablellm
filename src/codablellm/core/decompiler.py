import importlib

from abc import ABC, abstractmethod
from codablellm.core.function import DecompiledFunction
from codablellm.core.utils import PathLike, is_binary
from pathlib import Path
from typing import Any, Final, Iterable, List, Optional, TypedDict, Sequence, Union, overload

from codablellm.core.dashboard import CallablePoolProgress, ProcessPoolProgress, Progress


class NamedDecompiler(TypedDict):
    name: str
    class_path: str


DECOMPILER: Final[NamedDecompiler] = {
    'name': 'Ghidra',
    'class_path': 'codablellm.decompilers.ghidra.Ghidra'
}


def set_decompiler(name: str, class_path: str) -> None:
    DECOMPILER['name'] = name
    DECOMPILER['class_path'] = class_path


class Decompiler(ABC):

    @abstractmethod
    def decompile(self, path: PathLike) -> Sequence[DecompiledFunction]:
        pass


def get_decompiler(*args: Any, **kwargs: Any) -> Decompiler:
    module_path, class_name = DECOMPILER['class_path'].rsplit('.', 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)(*args, **kwargs)


def _decompile(path: PathLike, *args: Any, **kwargs: Any) -> Sequence[DecompiledFunction]:
    return get_decompiler(*args, **kwargs).decompile(path)


class _CallableDecompiler(CallablePoolProgress[PathLike, Sequence[DecompiledFunction],
                                               List[DecompiledFunction]]):

    def __init__(self, paths: Union[PathLike, Sequence[PathLike]],
                 max_workers: Optional[int],
                 *args: Any, **kwargs: Any) -> None:
        bins: List[Path] = []
        if isinstance(paths, (Path, str)):
            paths = [paths]
        for path in paths:
            path = Path(path)
            bins.extend([b for b in path.glob('*') if is_binary(b)]
                        if path.is_dir() else [path])
        pool = ProcessPoolProgress(_decompile, paths, Progress('Decompiling binaries...', total=len(paths)),
                                   max_workers=max_workers, submit_args=args, submit_kwargs=kwargs)
        super().__init__(pool)

    def get_results(self) -> List[DecompiledFunction]:
        return [d for b in self.pool for d in b]


@overload
def decompile(paths: Union[PathLike, Sequence[PathLike]],
              as_callable_pool: bool = False, max_workers: Optional[int] = None,
              *args: Any, **kwargs: Any) -> List[DecompiledFunction]: ...


@overload
def decompile(paths: Union[PathLike, Sequence[PathLike]],
              as_callable_pool: bool = True, max_workers: Optional[int] = None,
              *args: Any, **kwargs: Any) -> _CallableDecompiler: ...


def decompile(paths: Union[PathLike, Sequence[PathLike]],
              as_callable_pool: bool = False, max_workers: Optional[int] = None,
              *args: Any, **kwargs: Any) -> Union[List[DecompiledFunction], _CallableDecompiler]:
    decompiler = _CallableDecompiler(paths, max_workers, *args, **kwargs)
    if as_callable_pool:
        return decompiler
    return decompiler()
