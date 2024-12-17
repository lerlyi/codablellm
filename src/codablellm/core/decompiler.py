import importlib

from abc import ABC, abstractmethod
from codablellm.core.function import DecompiledFunction
from codablellm.core.utils import PathLike, is_binary
from pathlib import Path
from typing import Any, Final, Iterable, List, Optional, TypedDict, Sequence, Union, overload

from codablellm.dashboard import ProcessPoolProgress, Progress, PoolHandlerArg


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


@overload
def decompile(paths: Union[PathLike, Sequence[PathLike]],
              as_handler_arg: bool = True,
              *args: Any, **kwargs: Any) -> PoolHandlerArg[PathLike, Sequence[DecompiledFunction], List[DecompiledFunction]]: ...


@overload
def decompile(paths: Union[PathLike, Sequence[PathLike]],
              as_handler_arg: bool = False,
              *args: Any, **kwargs: Any) -> List[DecompiledFunction]: ...


def decompile(paths: Union[PathLike, Sequence[PathLike]],
              as_handler_arg: bool = False,
              *args: Any, **kwargs: Any) -> Union[List[DecompiledFunction],
                                                  PoolHandlerArg[PathLike,
                                                                 Sequence[DecompiledFunction],
                                                                 List[DecompiledFunction]]]:
    bins: List[Path] = []
    if isinstance(paths, (Path, str)):
        paths = [paths]
    for path in paths:
        path = Path(path)
        bins.extend([b for b in path.glob('*') if is_binary(b)]
                    if path.is_dir() else [path])
    progress = ProcessPoolProgress(_decompile, paths, Progress('Decompiling binaries...', total=len(paths)),
                                   submit_args=args, submit_kwargs=kwargs)
    if not as_handler_arg:
        progress = yield progress
    with progress:
        return [d for b in progress for d in b]
