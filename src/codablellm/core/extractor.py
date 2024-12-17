import importlib
import itertools
import logging

from abc import ABC, abstractmethod
from codablellm.core.function import SourceFunction
from codablellm.core.utils import PathLike
from pathlib import Path
from typing import Any, Final, Generator, Iterable, List, Literal, Mapping, Optional, OrderedDict, Sequence, Tuple, Union, overload

from codablellm.core.dashboard import ProcessPoolProgress, Progress, PoolHandlerArg

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


@overload
def extract(path: PathLike, *args: Any,
            as_handler_arg: bool = False, max_workers: Optional[int] = None,
            accurate_progress: bool = True,
            **kwargs: Any) -> List[SourceFunction]: ...


@overload
def extract(path: PathLike, *args: Any,
            as_handler_arg: bool = True, max_workers: Optional[int] = None,
            accurate_progress: bool = True,
            **kwargs: Any) -> PoolHandlerArg[Tuple[Extractor, Path],
                                             Sequence[SourceFunction], List[SourceFunction]]: ...


def extract(path: PathLike, *args: Any,
            as_handler_arg: bool = False, max_workers: Optional[int] = None,
            accurate_progress: bool = True,
            **kwargs: Any) -> Union[List[SourceFunction],
                                    PoolHandlerArg[Tuple[Extractor, Path],
                                                   Sequence[SourceFunction], List[SourceFunction]]]:

    def generate_extractors_and_files(path: PathLike, *args, **kwargs) -> Generator[Tuple[Extractor, Path], None, None]:
        for language in EXTRACTORS:
            extractor = get_extractor(language, *args, **kwargs)
            for file in extractor.get_extractable_files(path):
                yield extractor, file

    if accurate_progress:
        extractors_and_files = list(
            generate_extractors_and_files(path, *args, **kwargs))
        total = len(extractors_and_files)
    else:
        extractors_and_files = generate_extractors_and_files(
            path, *args, **kwargs)
        total = None
    progress = ProcessPoolProgress(_extract, extractors_and_files, Progress('Extracting functions...',
                                                                            total=total),
                                   max_workers=max_workers)
    if as_handler_arg:
        yield progress
    with progress:
        return [f for e in progress for f in e]
