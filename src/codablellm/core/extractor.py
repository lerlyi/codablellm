import importlib
import itertools
import logging

from abc import ABC, abstractmethod
from codablellm.core.function import SourceFunction
from codablellm.core.utils import PathLike
from concurrent.futures import Future, ProcessPoolExecutor
from pathlib import Path
from typing import Any, Final, Generator, Iterable, List, Literal, Mapping, Optional, OrderedDict, Sequence

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


def extract(path: PathLike, languages: Iterable[str] = EXTRACTORS.keys()) -> List[SourceFunction]:

    def callback(future: Future, results: List[SourceFunction], errors: List[int]) -> None:
        if not future.cancelled():
            exception = future.exception()
            if exception:
                errors[0] += 1
            else:
                results.append(future.result())

    new_results: List[SourceFunction] = []
    extracted_functions: List[SourceFunction] = []
    errors = [0]
    with ProcessPoolExecutor() as executor:
        futures = [executor.submit(_extract, l, path) for l in languages]
        for future in futures:
            future.add_done_callback(lambda f: callback(f, new_results,
                                                        errors))
        while not all(f.done() for f in futures):
            while any(new_results):
                extracted_functions.append(new_results.pop())
    return extracted_functions
