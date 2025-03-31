'''
Module containing functions for managing and registering source code extractors.

Source code extractors are responsible for parsing and extracting function definitions from different programming languages.
'''

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import importlib
import logging
from pathlib import Path
from typing import (
    Any, Callable, Dict, Final, List, Literal, Mapping, NamedTuple, Optional, OrderedDict,
    Sequence, Set
)

from prefect import flow, task

from codablellm.core.function import SourceFunction
from codablellm.core.utils import PathLike


class RegisteredExtractor(NamedTuple):
    language: str
    class_path: str


_EXTRACTORS: Final[OrderedDict[str, RegisteredExtractor]] = OrderedDict({
    'C': RegisteredExtractor('C', 'codablellm.languages.c.CExtractor')
})

logger = logging.getLogger('codablellm')


def get_registered() -> Sequence[RegisteredExtractor]:
    return list(_EXTRACTORS.values())


def register(language: str, class_path: str,
             order: Optional[Literal['first', 'last']] = None) -> None:
    '''
    Registers a new source code extractor for a given language.

    Parameters:
        language: The name of the language (e.g., "C", "Python") to associate with the extractor.
        class_path: The full import path to the extractor class.
        order: Optional order for insertion. If 'first', prepends the extractor; if 'last', appends it.
    '''
    registered_extractor = RegisteredExtractor('C', class_path)
    if _EXTRACTORS.setdefault(language, registered_extractor) != registered_extractor:
        raise ValueError(f'"{language}" is already a registered extractor')
    if order:
        _EXTRACTORS.move_to_end(language, last=order == 'last')
    # Instantiate extractor to ensure it can be properly imported
    try:
        create_extractor(language)
    except:
        logger.error(f'Could not create "{language}" extractor')
        unregister(language)
        raise
    logger.info(f'Registered "{language}" extractor at "{class_path}"')


def unregister(language: str) -> None:
    del _EXTRACTORS[language]
    logger.info(f'Unregistered "{language}" extractor')


def unregister_all() -> None:
    _EXTRACTORS.clear()
    logger.info('Unregistered all extractors')


def set_registered(extractors: Mapping[str, str]) -> None:
    '''
    Replaces all existing source code extractors with a new set.

    Parameters:
        extractors: A mapping from language names to extractor class paths.
    '''
    unregister_all()
    for language, class_path in extractors.items():
        register(language, class_path)


class Extractor(ABC):
    '''
    Abstract base class for source code extractors.

    Extractors are responsible for parsing source code files and returning extracted function
    definitions as `SourceFunction` instances.
    '''

    @abstractmethod
    def extract(self, file_path: PathLike, repo_path: Optional[PathLike] = None) -> Sequence[SourceFunction]:
        '''
        Extracts functions from the given source code file.

        Parameters:
            file_path: The path to the source file.
            repo_path: Optional repository root path to calculate relative function scopes.

        Returns:
            A sequence of `SourceFunction` instances extracted from the file.
        '''
        pass

    @abstractmethod
    def get_extractable_files(self, path: PathLike) -> Set[Path]:
        '''
        Retrieves all files that can be processed by the extractor from the given path.

        Parameters:
            path: A file or directory path to search for extractable files.

        Returns:
            A sequence of `Path` objects representing extractable source files.
        '''
        pass


def create_extractor(language: str, *args: Any, **kwargs: Any) -> Extractor:
    '''
    Retrieves the registered extractor instance for the specified language.

    Parameters:
        language: The name of the language for which to retrieve an extractor.
        *args: Positional arguments passed to the extractor's constructor.
        **kwargs: Keyword arguments passed to the extractor's constructor.

    Returns:
        An instance of the extractor class for the given language.

    Raises:
        ExtractorNotFound: If no extractor is registered for the specified language.
    '''
    if language in _EXTRACTORS:
        module_path, class_name = _EXTRACTORS[language].class_path.rsplit(
            '.', 1)
        module = importlib.import_module(module_path)
        return getattr(module, class_name)(*args, **kwargs)
    raise ValueError(f'"{language}" is not a registered extractor')


Transform = Callable[[SourceFunction], SourceFunction]
'''
A callable object that transforms a source code function into another source code function.
'''


@dataclass(frozen=True)
class ExtractConfig:
    '''
    Configuration for extracting source code functions.
    '''
    max_workers: Optional[int] = None
    '''
    Maximum number of files to extract functions in parallel.
    '''
    accurate_progress: bool = True
    '''
    Whether to accurately track progress by counting extractable files in advance. This may take
    longer to start but provides more accurate progress tracking.
    '''
    transform: Optional[Transform] = None
    '''
    An optional transformation to apply to each source code function.
    '''
    exclusive_subpaths: Set[Path] = field(default_factory=set)
    '''
    A set of subpaths to exclusively extract functions from. If specified, only these subpaths will be extracted.
    '''
    exclude_subpaths: Set[Path] = field(default_factory=set)
    '''
    A set of subpaths to exclude from extraction. If specified, these subpaths will be ignored.
    '''
    checkpoint: int = 10
    '''
    The number of steps between saving checkpoints. Set to 0 to disable checkpoints.
    '''
    use_checkpoint: bool = True
    '''
    `True` if a checkpoint file should be loaded and used to resume extraction.
    '''
    extract_as_repo: bool = True
    '''
    `True` if the path should be treated as a repository root for calculating relative function scopes.
    '''
    extractor_args: Dict[str, Sequence[Any]] = field(default_factory=dict)
    '''
    Positional arguments to pass to the extractor's `__init__` method. The keys are language
    names. The values are sequences of arguments. For example, `{'C': [arg1, arg2]}`.
    '''
    extractor_kwargs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    '''
    Keyword arguments to pass to the extractor's `__init__` method. The keys are language names.
    The values are dictionaries of keyword arguments. For example, `{'C': {'kwarg1': value1}}`.
    '''

    def __post_init__(self) -> None:
        if self.max_workers and self.max_workers < 1:
            raise ValueError('Max workers must be a positive integer')
        if self.exclude_subpaths & self.exclusive_subpaths:
            raise ValueError('Cannot have overlapping paths in exclude_subpaths and '
                             'exclusive_subpaths')
        if self.checkpoint < 0:
            raise ValueError('Checkpoint must be a non-negative integer')


@task
def extract_directory_task(
    path: PathLike,
    config: ExtractConfig = ExtractConfig()
) -> List[SourceFunction]:
    '''
    Extracts source functions from the given path using the specified configuration.

    If `as_callable_pool` is `True`, returns a deferred callable extractor that can be executed later,  
    typically used for progress bar display or asynchronous processing.

    Parameters:
        path: The file or directory path from which to extract functions.
        config: Extraction configuration options.
        as_callable_pool: If `True`, returns a callable extractor for deferred execution.

    Returns:
        Either a list of extracted `SourceFunction` instances or a `_CallableExtractor` for deferred execution.
    '''
    # Collect extractable files
    logger.info('Collecting extractable source code files...')
    file_extractor_map: Dict[Path, Extractor] = {}
    for language, _ in get_registered():
        extractor = create_extractor(language, *config.extractor_args.get(language, []),
                                     **config.extractor_kwargs.get(language, {}))
        # Locate extractable files
        files = extractor.get_extractable_files(path)
        if not any(files):
            logger.debug(f'No "{language}" files were located')
        for file in files:
            if file_extractor_map.setdefault(file, extractor) != extractor:
                logger.info(
                    f'Extractor was already specified for {file.name}'
                )
    if not any(file_extractor_map):
        logger.warning('No source code files found to extract')
    # Submit extraction tasks
    logger.info('Submitting extraction tasks...')
    futures = [task(extractor.extract).submit(file, repo_path=path)
               for file, extractor in file_extractor_map.items()]
    functions = [
        function for future in futures for function in future.result()]
    if config.transform:
        # Apply transformation
        logger.info('Applying transformation...')
        functions = task(config.transform).map(functions).result()
    return functions


@flow
def extract(
    *paths: PathLike,
    config: ExtractConfig = ExtractConfig()
) -> List[SourceFunction]:
    futures = [extract_directory_task.submit(path, config=config)
               for path in paths]
    return [function
            for future in futures
            for function in future.result()]
