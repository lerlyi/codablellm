import importlib
import logging

from abc import ABC, abstractmethod
from codablellm.core.function import SourceFunction
from codablellm.core.utils import PathLike
from pathlib import Path
from typing import Any, Final, List, Literal, Mapping, Optional, OrderedDict, Sequence, Union, overload

from codablellm.dashboard import ProcessPoolProgress, Progress, PoolHandlerArg

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


def _extract(language: str, path: PathLike, *args: Any, **kwargs: Any) -> Sequence[SourceFunction]:
    return get_extractor(language, *args, **kwargs).extract(path)


@overload
def extract(path: PathLike, *args: Any,
            as_handler_arg: bool = False, max_workers: Optional[int] = None,
            **kwargs: Any) -> List[SourceFunction]: ...


@overload
def extract(path: PathLike, *args: Any,
            as_handler_arg: bool = True, max_workers: Optional[int] = None,
            **kwargs: Any) -> PoolHandlerArg[str, Sequence[SourceFunction], List[SourceFunction]]: ...


def extract(path: PathLike, *args: Any,
            as_handler_arg: bool = False, max_workers: Optional[int] = None,
            **kwargs: Any) -> Union[List[SourceFunction],
                                    PoolHandlerArg[str, Sequence[SourceFunction], List[SourceFunction]]]:
    progress = ProcessPoolProgress(_extract, EXTRACTORS.keys(), Progress('Extracting functions...'),
                                   max_workers=max_workers, submit_args=(path, *args), submit_kwargs=kwargs)
    if as_handler_arg:
        yield progress
    with progress:
        return [f for e in progress for f in e]
