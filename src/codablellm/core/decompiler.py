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
from typing import Any, Collection, Dict, List, Mapping, NamedTuple, Optional, Sequence, Set, Union

from prefect import flow, task

from codablellm.core.function import DecompiledFunction
from codablellm.core.utils import PathLike, is_binary
from codablellm.exceptions import DecompilerNotFound

logger = logging.getLogger('codablellm')


class RegisteredDecompiler(NamedTuple):
    name: str
    class_path: str


_decompiler: RegisteredDecompiler = RegisteredDecompiler(
    'Ghidra', 'codablellm.decompilers.ghidra.Ghidra'
)


def set(name: str, class_path: str) -> None:
    '''
    Sets the decompiler used by `codablellm`.

    Parameters:
        class_path:  The fully qualified class path (in the form `module.submodule.ClassName`) of the subclass of `Decompiler` to use.
    '''
    global _decompiler
    old_decompiler = _decompiler
    _decompiler = RegisteredDecompiler(name, class_path)
    # Instantiate decompiler to ensure it can be properly imported
    try:
        create_decompiler()
    except:
        logger.error(f'Could not create "{name}" extractor')
        _decompiler = old_decompiler
        raise
    logger.info(f'Using "{name}" ({class_path}) as the decompiler')


def get() -> RegisteredDecompiler:
    return _decompiler


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


def create_decompiler(*args: Any, **kwargs: Any) -> Decompiler:
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
    module_path, class_name = _decompiler.class_path.rsplit('.', 1)
    try:
        module = importlib.import_module(module_path)
        return getattr(module, class_name)(*args, **kwargs)
    except (ModuleNotFoundError, AttributeError) as e:
        raise DecompilerNotFound('Could not import '
                                 f'"{module_path}.{class_name}"') from e


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
    decompiler_kwargs: Mapping[str, Any] = field(default_factory=dict)
    '''
    Keyword arguments to pass to the decompiler's `__init__` method.
    '''

    def __post_init__(self) -> None:
        if self.max_workers and self.max_workers < 1:
            raise ValueError('Max workers must be a positive integer')


@task
def decompile_task(*paths: PathLike,
                   config: DecompileConfig) -> List[DecompiledFunction]:
    '''
    Decompiles binaries and extracts decompiled functions from the given path or list of paths.

    Parameters:
        paths: A single path or sequence of paths pointing to binary files or directories containing binaries.
        config: Decompilation configuration options.
        as_callable_pool: If `True`, returns a callable pool for deferred execution, typically used for progress bar handling or asynchronous processing.

    Returns:
        Either a list of `DecompiledFunction` instances or a `_CallableDecompiler` for deferred execution.
    '''
    bins: List[Path] = []
    # Collect binary files
    if isinstance(paths, (Path, str)):
        paths = (paths,)
    for path in paths:
        path = Path(path)
        # If a path is a directory, glob all child binaries
        bins.extend([b for b in path.glob('*') if is_binary(b)]
                    if path.is_dir() else [path])
    if not any(bins):
        logger.warning('No binaries found to decompile')
    # Create decompiler
    decompiler = create_decompiler(*config.decompiler_args,
                                   **config.decompiler_kwargs)
    # Submit decompile tasks
    logger.info(f'Submitting {get().name} decompile tasks...')
    futures = [task(decompiler.decompile).submit(bin) for bin in bins]
    return [function for future in futures for function in future.result()]


@flow
def decompile(*paths: PathLike,
              config: DecompileConfig) -> List[DecompiledFunction]:
    return decompile_task(*paths, config=config)
