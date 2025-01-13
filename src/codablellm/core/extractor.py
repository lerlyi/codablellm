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
from codablellm.core.utils import PathLike
from codablellm.exceptions import ExtractorNotFound

EXTRACTORS: Final[OrderedDict[str, str]] = OrderedDict({
    'C': 'codablellm.languages.c.CExtractor'
})

logger = logging.getLogger('codablellm')


def add_extractor(language: str, class_path: str,
                  order: Optional[Literal['first', 'last']] = None) -> None:
    EXTRACTORS[language] = class_path
    if order:
        logger.info('Prepended ' if order == 'first' else 'Appended '
                    f'{language} source code extractor "{class_path}"')
        EXTRACTORS.move_to_end(language, last=order == 'last')
    else:
        logger.info(f'Added {language} source code extractor "{class_path}"')


def set_extractors(extractors: Mapping[str, str]) -> None:
    EXTRACTORS.clear()
    logger.info('Source code extractors cleared')
    for language, class_path in extractors.items():
        add_extractor(language, class_path)


class Extractor(ABC):

    @abstractmethod
    def extract(self, path: PathLike) -> Sequence[SourceFunction]:
        pass

    @abstractmethod
    def get_extractable_files(self, path: PathLike) -> Sequence[Path]:
        pass


def get_extractor(language: str, *args: Any, **kwargs: Any) -> Extractor:
    if language in EXTRACTORS:
        module_path, class_name = EXTRACTORS[language].rsplit('.', 1)
        module = importlib.import_module(module_path)
        return getattr(module, class_name)(*args, **kwargs)
    raise ExtractorNotFound(f'Unsupported language: {language}')


def _extract(extractor_and_file: Tuple[Extractor, Path]) -> Sequence[SourceFunction]:
    extractor, file = extractor_and_file
    return extractor.extract(file)


EXTRACTOR_CHECKPOINT_PREFIX: Final[str] = 'codablellm_extractor'


def get_checkpoint_files() -> List[Path]:
    return utils.get_checkpoint_files(EXTRACTOR_CHECKPOINT_PREFIX)


def save_checkpoint_file(source_code_functions: List[SourceFunction]) -> None:
    utils.save_checkpoint_file(EXTRACTOR_CHECKPOINT_PREFIX,
                               source_code_functions)


def load_checkpoint_data() -> List[SourceFunction]:
    return utils.load_checkpoint_data(EXTRACTOR_CHECKPOINT_PREFIX, delete_on_load=True)


@dataclass(frozen=True)
class ExtractConfig:
    max_workers: Optional[int] = None
    accurate_progress: bool = True
    transform: Optional[Callable[[SourceFunction], SourceFunction]] = None
    exclusive_subpaths: Set[Path] = field(default_factory=set)
    exclude_subpaths: Set[Path] = field(default_factory=set)
    checkpoint: int = 10
    use_checkpoint: bool = True
    extractor_args: Dict[str, Sequence[Any]] = field(default_factory=dict)
    extractor_kwargs: Dict[str, Dict[str, Any]] = field(default_factory=dict)

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


class _CallableExtractor(CallablePoolProgress[Tuple[Extractor, Path], Sequence[SourceFunction],
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

        def generate_extractors_and_files(path: PathLike, extractor_args: Dict[str, Sequence[Any]],
                                          extractor_kwargs: Dict[str, Dict[str, Any]]) -> Generator[Tuple[Extractor, Path], None, None]:
            for language in EXTRACTORS:
                extractor = get_extractor(language, *extractor_args.get(language, []),
                                          **extractor_kwargs.get(language, {}))
                for file in extractor.get_extractable_files(path):
                    if not any(is_relative_to(p, file) for p in config.exclude_subpaths) \
                            or any(is_relative_to(p, file) for p in config.exclusive_subpaths):
                        yield extractor, file

        if config.accurate_progress:
            extractors_and_files = list(generate_extractors_and_files(path, config.extractor_args,
                                                                      config.extractor_kwargs))
            total = len(extractors_and_files)
            logger.info(f'Located {total} extractable source code files')
        else:
            extractors_and_files = generate_extractors_and_files(path, config.extractor_args,
                                                                 config.extractor_kwargs)
            total = None
        pool = ProcessPoolProgress(_extract, extractors_and_files, Progress('Extracting functions...',
                                                                            total=total),
                                   max_workers=config.max_workers)
        super().__init__(pool)
        self.transform = config.transform

    def get_results(self) -> List[SourceFunction]:
        results: Dict[str, SourceFunction] = {}
        if self.use_checkpoint:
            results = {f.uid: f for f in load_checkpoint_data()}
            if results:
                logger.info(f'Loaded {len(results)} checkpoint results')
        for functions in self.pool:
            for function in functions:
                if self.transform:
                    try:
                        function = self.transform(function)
                    except Exception as e:
                        logger.warning('Error occured during transformation: '
                                       f'{type(e).__name__}: {e}')
                        continue
                if function.uid in results:
                    logger.warning(f'Function "{function.uid}" was already extracted. Ignoring'
                                   'duplicate entry')
                else:
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
    extractor = _CallableExtractor(path, config)
    if as_callable_pool:
        return extractor
    return extractor()
