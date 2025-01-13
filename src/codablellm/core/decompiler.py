from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import importlib
import logging
from pathlib import Path
from typing import Any, Dict, Final, List, Literal, Optional, TypedDict, Sequence, Union, overload

from codablellm.core.dashboard import CallablePoolProgress, ProcessPoolProgress, Progress
from codablellm.core.function import DecompiledFunction
from codablellm.core.utils import PathLike, is_binary

logger = logging.getLogger('codablellm')


class NamedDecompiler(TypedDict):
    class_path: str


DECOMPILER: Final[NamedDecompiler] = {
    'class_path': 'codablellm.decompilers.ghidra.Ghidra'
}


def set_decompiler(class_path: str) -> None:
    DECOMPILER['class_path'] = class_path
    logger.info(f'Using "{class_path}" as the decompiler')


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


@dataclass(frozen=True)
class DecompileConfig:
    max_workers: Optional[int] = None
    decompiler_args: Sequence[Any] = field(default_factory=list)
    decompiler_kwargs: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.max_workers and self.max_workers < 1:
            raise ValueError('Max workers must be a positive integer')


class _CallableDecompiler(CallablePoolProgress[PathLike, Sequence[DecompiledFunction],
                                               List[DecompiledFunction]]):

    def __init__(self, paths: Union[PathLike, Sequence[PathLike]],
                 config: DecompileConfig) -> None:
        bins: List[Path] = []
        if isinstance(paths, (Path, str)):
            paths = [paths]
        for path in paths:
            path = Path(path)
            bins.extend([b for b in path.glob('*') if is_binary(b)]
                        if path.is_dir() else [path])
        pool = ProcessPoolProgress(_decompile, paths, Progress('Decompiling binaries...', total=len(paths)),
                                   max_workers=config.max_workers,
                                   submit_args=tuple(config.decompiler_args),
                                   submit_kwargs=config.decompiler_kwargs)
        super().__init__(pool)

    def get_results(self) -> List[DecompiledFunction]:
        return [d for b in self.pool for d in b]


@overload
def decompile(paths: Union[PathLike, Sequence[PathLike]],
              config: DecompileConfig = DecompileConfig(),
              as_callable_pool: Literal[False] = False) -> List[DecompiledFunction]: ...


@overload
def decompile(paths: Union[PathLike, Sequence[PathLike]],
              config: DecompileConfig = DecompileConfig(),
              as_callable_pool: Literal[True] = True) -> _CallableDecompiler: ...


def decompile(paths: Union[PathLike, Sequence[PathLike]],
              config: DecompileConfig = DecompileConfig(),
              as_callable_pool: bool = False) -> Union[List[DecompiledFunction], _CallableDecompiler]:
    decompiler = _CallableDecompiler(paths, config)
    if as_callable_pool:
        return decompiler
    return decompiler()
