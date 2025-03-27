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
    Any, Callable, Dict, Final, Generator, List, Literal, Mapping, Optional, OrderedDict, Sequence, Set,
    Tuple, Union, overload)

from codablellm.core import utils
from codablellm.core.dashboard import CallablePoolProgress, ProcessPoolProgress, Progress
from codablellm.core.function import SourceFunction
from codablellm.core.utils import PathLike, benchmark_function
from codablellm.exceptions import ExtractorNotFound

EXTRACTORS: Final[OrderedDict[str, str]] = OrderedDict({
    'C': 'codablellm.languages.c.CExtractor'
})

logger = logging.getLogger('codablellm')


def add_extractor(language: str, class_path: str,
                  order: Optional[Literal['first', 'last']] = None) -> None:
    '''
    Registers a new source code extractor for a given language.

    Parameters:
        language: The name of the language (e.g., "C", "Python") to associate with the extractor.
        class_path: The full import path to the extractor class.
        order: Optional order for insertion. If 'first', prepends the extractor; if 'last', appends it.
    '''
    EXTRACTORS[language] = class_path
    if order:
        logger.info('Prepended ' if order == 'first' else 'Appended '
                    f'{language} source code extractor "{class_path}"')
        EXTRACTORS.move_to_end(language, last=order == 'last')
    else:
        logger.info(f'Added {language} source code extractor "{class_path}"')


def set_extractors(extractors: Mapping[str, str]) -> None:
    '''
    Replaces all existing source code extractors with a new set.

    Parameters:
        extractors: A mapping from language names to extractor class paths.
    '''
    EXTRACTORS.clear()
    logger.info('Source code extractors cleared')
    for language, class_path in extractors.items():
        add_extractor(language, class_path)


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
    def get_extractable_files(self, path: PathLike) -> Sequence[Path]:
        '''
        Retrieves all files that can be processed by the extractor from the given path.

        Parameters:
            path: A file or directory path to search for extractable files.

        Returns:
            A sequence of `Path` objects representing extractable source files.
        '''
        pass


def get_extractor(language: str, *args: Any, **kwargs: Any) -> Extractor:
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
    if language in EXTRACTORS:
        module_path, class_name = EXTRACTORS[language].rsplit('.', 1)
        module = importlib.import_module(module_path)
        return getattr(module, class_name)(*args, **kwargs)
    raise ExtractorNotFound(f'Unsupported language: {language}')


def _extract(extractor_and_paths: Tuple[Extractor, Path, Optional[Path]]) -> Sequence[SourceFunction]:
    extractor, file, repo = extractor_and_paths
    logger.debug(f'Extracting {file}...')
    return extractor.extract(file, repo_path=repo)


EXTRACTOR_CHECKPOINT_PREFIX: Final[str] = 'codablellm_extractor'


def get_checkpoint_files() -> List[Path]:
    '''
    Retrieves all checkpoint files related to source function extraction.

    Returns:
        A list of checkpoint files.
    '''
    return utils.get_checkpoint_files(EXTRACTOR_CHECKPOINT_PREFIX)


def save_checkpoint_file(source_code_functions: List[SourceFunction]) -> None:
    '''
    Saves a checkpoint file containing extracted source functions.

    Parameters:
        source_code_functions: A list of `SourceFunction` instances to save as checkpoint data.
    '''
    utils.save_checkpoint_file(EXTRACTOR_CHECKPOINT_PREFIX,
                               source_code_functions)


def load_checkpoint_data() -> List[SourceFunction]:
    '''
    Loads checkpoint data for source functions and clears the checkpoint files after loading.

    Returns:
        A list of `SourceFunction` instances restored from checkpoint data.
    '''
    return [SourceFunction.from_json(j)  # type: ignore
            for j in utils.load_checkpoint_data(EXTRACTOR_CHECKPOINT_PREFIX, delete_on_load=True)]


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
        for extractor in self.extractor_args:
            if extractor not in EXTRACTORS:
                raise ValueError(f'"{extractor}" is not a known extractor')
        for extractor in self.extractor_kwargs:
            if extractor not in EXTRACTORS:
                raise ValueError(f'"{extractor}" is not a known extractor')


class _CallableExtractor(CallablePoolProgress[Tuple[Extractor, Path, Optional[Path]], Sequence[SourceFunction],
                                              List[SourceFunction]]):

    def __init__(self, path: PathLike, config: ExtractConfig) -> None:

        def is_relative_to(parent: Path, child: Path) -> bool:
            try:
                parent.relative_to(child)
            except ValueError:
                return False
            return True

        if config.exclude_subpaths & config.exclusive_subpaths:
            raise ValueError('Cannot have overlapping paths in exclude_subpaths and '
                             'exclusive_subpaths')
        if config.checkpoint < 0:
            raise ValueError('Checkpoint must be a non-negative integer')
        self.checkpoint = config.checkpoint
        self.use_checkpoint = config.use_checkpoint
        path = Path(path)
        if not all(is_relative_to(path, p)
                   for subpaths in [config.exclusive_subpaths, config.exclude_subpaths] for p in subpaths):
            raise ValueError('All subpaths must be relative to the '
                             'repository.')

        def generate_extractors_and_paths(path: PathLike, extract_as_repo: bool,
                                          extractor_args: Dict[str, Sequence[Any]],
                                          extractor_kwargs: Dict[str, Dict[str, Any]]) -> Generator[Tuple[Extractor, Path, Optional[Path]], None, None]:
            repo_path = None if not extract_as_repo else Path(path)
            for language in EXTRACTORS:
                extractor = get_extractor(language, *extractor_args.get(language, []),
                                          **extractor_kwargs.get(language, {}))
                for file in extractor.get_extractable_files(path):
                    if not any(is_relative_to(p, file) for p in config.exclude_subpaths) \
                            or any(is_relative_to(p, file) for p in config.exclusive_subpaths):
                        yield extractor, file, repo_path

        if config.accurate_progress:
            extractors_and_paths = list(generate_extractors_and_paths(path, config.extract_as_repo,
                                                                      config.extractor_args,
                                                                      config.extractor_kwargs))
            total = len(extractors_and_paths)
            logger.info(f'Located {total} extractable source code files')
        else:
            extractors_and_paths = generate_extractors_and_paths(path, config.extract_as_repo,
                                                                 config.extractor_args,
                                                                 config.extractor_kwargs)
            total = None
        if not any(extractors_and_paths):
            logger.warning('No files found to extract functions from')
        pool = ProcessPoolProgress(_extract, extractors_and_paths, Progress('Extracting functions...',
                                                                            total=total),
                                   max_workers=config.max_workers)
        super().__init__(pool)
        self.transform = config.transform

    @benchmark_function('Extracting source code functions')
    def get_results(self) -> List[SourceFunction]:
        results: Dict[str, SourceFunction] = {}
        if self.use_checkpoint:
            results = {f.uid: f for f in load_checkpoint_data()}
            if results:
                logger.info(f'Loaded {len(results)} checkpoint results')
        for functions in self.pool:
            for function in functions:
                if function.uid in results:
                    logger.warning(f'Function "{function.uid}" was already extracted. Ignoring '
                                   'duplicate entry')
                    continue
                elif self.transform:
                    try:
                        logger.debug(f'Transforming function "{function.name}"...')
                        function = self.transform(function)
                    except Exception as e:
                        logger.warning('Error occurred during transformation: '
                                       f'{type(e).__name__}: {e}')
                        continue
                results[function.uid] = function
                if self.checkpoint > 0 and len(results) % self.checkpoint == 0:
                    save_checkpoint_file(list(results.values()))
                    logger.info('Extraction checkpoint saved')
        return list(results.values())


@overload
def extract(path: PathLike, config: ExtractConfig = ExtractConfig(),
            as_callable_pool: Literal[False] = False) -> List[SourceFunction]: ...


@overload
def extract(path: PathLike, config: ExtractConfig = ExtractConfig(),
            as_callable_pool: Literal[True] = True) -> _CallableExtractor: ...


def extract(path: PathLike, config: ExtractConfig = ExtractConfig(),
            as_callable_pool: bool = False) -> Union[List[SourceFunction],
                                                     _CallableExtractor]:
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
    extractor = _CallableExtractor(path, config)
    if as_callable_pool:
        return extractor
    return extractor()
