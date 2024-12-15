import importlib
import itertools
import logging

from abc import ABC, abstractmethod
from codablellm.core.function import SourceFunction
from codablellm.core.utils import PathLike
from concurrent.futures import Future, ProcessPoolExecutor
from pathlib import Path
from typing import Any, Final, Generator, Iterable, List, Literal, Mapping, Optional, OrderedDict, Sequence, Union

from codablellm.dashboard import ProcessPoolProgress, Progress

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


def _extract(language: str, path: PathLike) -> Sequence[SourceFunction]:
    return get_extractor(language).extract(path)


def extract(path: PathLike, get_progress: bool = False) -> Generator[Union[ProcessPoolProgress, SourceFunction], None, None]:

    with ProcessPoolProgress(_extract, EXTRACTORS.keys(), Progress('Extracting functions...'),
                             submit_args=(path,)) as progress:
        if get_progress:
            yield progress
        yield from (f for e in progress for f in e)
