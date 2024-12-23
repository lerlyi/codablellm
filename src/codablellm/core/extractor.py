from abc import ABC, abstractmethod
import importlib
import logging
from pathlib import Path
from typing import (
    Any, Callable, Final, Generator, List, Literal, Mapping, Optional, OrderedDict, Sequence, Set,
    Tuple, Union, overload)

from codablellm.core.dashboard import CallablePoolProgress, ProcessPoolProgress, Progress
from codablellm.core.function import SourceFunction
from codablellm.core.utils import PathLike

EXTRACTORS: Final[OrderedDict[str, str]] = OrderedDict({
    'C': 'codablellm.languages.c.CExtractor'
})

logger = logging.getLogger('codablellm')


def add_extractor(language: str, class_path: str,
                  order: Optional[Literal['first', 'last']] = None) -> None:
    EXTRACTORS[language] = class_path
    if order:
        EXTRACTORS.move_to_end(language, last=order == 'last')


def set_extractors(extractors: Mapping[str, str]) -> None:
    EXTRACTORS.clear()
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
    raise ValueError(f'Unsupported language: {language}')


def _extract(extractor_and_file: Tuple[Extractor, Path]) -> Sequence[SourceFunction]:
    extractor, file = extractor_and_file
    return extractor.extract(file)


class _CallableExtractor(CallablePoolProgress[Tuple[Extractor, Path], Sequence[SourceFunction],
                                              List[SourceFunction]]):

    def __init__(self, path: PathLike, *args: Any,
                 max_workers: Optional[int],
                 accurate_progress: bool,
                 transform: Optional[Callable[[SourceFunction], SourceFunction]],
                 subpaths: Set[Path],
                 subpaths_mode: Literal['exclude', 'exclusive'],
                 **kwargs: Any) -> None:

        def is_relative_to(parent: Path, child: Path) -> bool:
            try:
                parent.relative_to(child)
            except ValueError:
                return False
            return True

        path = Path(path)
        if not all(is_relative_to(path, p) for p in subpaths):
            raise ValueError('All subpaths must be relative to the '
                             'repository.')

        def generate_extractors_and_files(path: PathLike, *args, **kwargs) -> Generator[Tuple[Extractor, Path], None, None]:
            for language in EXTRACTORS:
                extractor = get_extractor(language, *args, **kwargs)
                for file in extractor.get_extractable_files(path):
                    if subpaths_mode == 'exclude' and not any(is_relative_to(p, file) for p in subpaths) \
                            or subpaths_mode == 'exclusive' and any(is_relative_to(p, file) for p in subpaths):
                        yield extractor, file

        if accurate_progress:
            extractors_and_files = list(generate_extractors_and_files(path, *args,
                                                                      **kwargs))
            total = len(extractors_and_files)
        else:
            extractors_and_files = generate_extractors_and_files(path, *args,
                                                                 **kwargs)
            total = None
        pool = ProcessPoolProgress(_extract, extractors_and_files, Progress('Extracting functions...',
                                                                            total=total),
                                   max_workers=max_workers)
        super().__init__(pool)
        self.transform = transform

    def get_results(self) -> List[SourceFunction]:
        return [self.transform(f) for e in self.pool for f in e] if self.transform \
            else [f for e in self.pool for f in e]


@overload
def extract(path: PathLike, *args: Any,
            as_callable_pool: bool = False, max_workers: Optional[int] = None,
            accurate_progress: bool = True,
            transform: Optional[Callable[[SourceFunction],
                                         SourceFunction]] = None,
            **kwargs: Any) -> List[SourceFunction]: ...


@overload
def extract(path: PathLike, *args: Any,
            as_callable_pool: bool = True, max_workers: Optional[int] = None,
            accurate_progress: bool = True,
            transform: Optional[Callable[[SourceFunction],
                                         SourceFunction]] = None,
            **kwargs: Any) -> _CallableExtractor: ...


def extract(path: PathLike, *args: Any,
            as_callable_pool: bool = False, max_workers: Optional[int] = None,
            accurate_progress: bool = True,
            transform: Optional[Callable[[SourceFunction],
                                         SourceFunction]] = None,
            **kwargs: Any) -> Union[List[SourceFunction],
                                    _CallableExtractor]:
    extractor = _CallableExtractor(path, *args, max_workers, accurate_progress, transform,
                                   **kwargs)
    if as_callable_pool:
        return extractor
    return extractor()
