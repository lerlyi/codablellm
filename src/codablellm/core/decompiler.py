'''
Module containing functions for decompiling binaries.

This module manages decompiler registration and configuration, allowing `codablellm` 
to use different backends for binary decompilation.
'''

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import importlib
import logging
from pathlib import Path
from typing import Any, Dict, Final, List, Literal, Optional, TypedDict, Sequence, Union, overload

from codablellm.core.dashboard import CallablePoolProgress, ProcessPoolProgress, Progress
from codablellm.core.function import DecompiledFunction
from codablellm.core.utils import PathLike, benchmark_function, is_binary
from codablellm.exceptions import DecompilerNotFound

logger = logging.getLogger('codablellm')


class NamedDecompiler(TypedDict):
    class_path: str


DECOMPILER: Final[NamedDecompiler] = {
    'class_path': 'codablellm.decompilers.ghidra.Ghidra'
}


def set_decompiler(class_path: str) -> None:
    '''
    Sets the decompiler used by `codablellm`.

    Parameters:
        class_path:  The fully qualified class path (in the form `module.submodule.ClassName`) of the subclass of `Decompiler` to use.
    '''
    DECOMPILER['class_path'] = class_path
    logger.info(f'Using "{class_path}" as the decompiler')


class Decompiler(ABC):
    '''
    Abstract base class for a decompiler that extracts decompiled functions from compiled binaries.
    '''

    @abstractmethod
    def decompile(self, path: PathLike) -> Sequence[DecompiledFunction]:
        '''
        Decompiles a binary and retrieves all decompiled functions contained in it.

        Parameters:
            path: The path to the binary file to be decompiled.

        Returns:
            A sequence of `DecompiledFunction` objects representing the functions extracted from the binary.
        '''
        pass


def get_decompiler(*args: Any, **kwargs: Any) -> Decompiler:
    '''
    Initializes an instance of the decompiler that is being used by `codablellm`.

    Parameters:
        args:  Positional arguments to pass to the decompiler's `__init__` method.
        kwargs:  Keyword arguments to pass to the decompiler's `__init__` method.

    Returns:
        An instance of the specified `Decompiler` subclass.

    Raises:
        DecompilerNotFound: If the specified decompiler cannot be imported or if the class cannot be found in the specified module.
    '''
    module_path, class_name = DECOMPILER['class_path'].rsplit('.', 1)
    try:
        module = importlib.import_module(module_path)
        return getattr(module, class_name)(*args, **kwargs)
    except (ModuleNotFoundError, AttributeError) as e:
        raise DecompilerNotFound('Could not import '
                                 f'"{module_path}.{class_name}"') from e


def _decompile(path: PathLike, *args: Any, **kwargs: Any) -> Sequence[DecompiledFunction]:
    logger.debug(f'Decompiling {Path(path).name}...')
    return get_decompiler(*args, **kwargs).decompile(path)


@dataclass(frozen=True)
class DecompileConfig:
    '''
    Configuration for decompiling binaries.
    '''
    max_workers: Optional[int] = None
    '''
    Maximum number of binaries to decompile in parallel.
    '''
    decompiler_args: Sequence[Any] = field(default_factory=list)
    '''
    Positional arguments to pass to the decompiler's `__init__` method.
    '''
    decompiler_kwargs: Dict[str, Any] = field(default_factory=dict)
    '''
    Keyword arguments to pass to the decompiler's `__init__` method.
    '''

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
            # If a path is a directory, glob all child binaries
            bins.extend([b for b in path.glob('*') if is_binary(b)]
                        if path.is_dir() else [path])
        if not any(bins):
            logger.warning('No binaries found to decompile')
        pool = ProcessPoolProgress(_decompile, bins, Progress('Decompiling binaries...', total=len(bins)),
                                   max_workers=config.max_workers,
                                   submit_args=tuple(config.decompiler_args),
                                   submit_kwargs=config.decompiler_kwargs)
        super().__init__(pool)

    @benchmark_function('Decompiling binaries')
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
    '''
    Decompiles binaries and extracts decompiled functions from the given path or list of paths.

    Parameters:
        paths: A single path or sequence of paths pointing to binary files or directories containing binaries.
        config: Decompilation configuration options.
        as_callable_pool: If `True`, returns a callable pool for deferred execution, typically used for progress bar handling or asynchronous processing.

    Returns:
        Either a list of `DecompiledFunction` instances or a `_CallableDecompiler` for deferred execution.
    '''
    decompiler = _CallableDecompiler(paths, config)
    if as_callable_pool:
        return decompiler
    return decompiler()
