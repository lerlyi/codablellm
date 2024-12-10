import importlib

from abc import ABC, abstractmethod
from typing import Dict, Final, Iterable, List, Sequence
from codablellm.core.function import Function
from codablellm.core.utils import PathLike

EXTRACTORS: Final[Dict[str, str]] = {}


class Extractor(ABC):

    @abstractmethod
    def extract(self, path: PathLike) -> Sequence[Function]:
        pass


def get_extractor(language: str) -> Extractor:
    if language in EXTRACTORS:
        module_path, class_name = EXTRACTORS[language].rsplit('.', 1)
        module = importlib.import_module(module_path)
        return getattr(module, class_name)()
    raise ValueError(f'Unsupported language: {language}')


def extract(path: PathLike, languages: Iterable[str] = EXTRACTORS.keys()) -> List[Function]:
    return [f for l in languages for f in get_extractor(l).extract(path)]
