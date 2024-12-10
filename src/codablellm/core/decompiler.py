import importlib

from abc import ABC, abstractmethod
from typing import Dict, Final, Sequence
from codablellm.core.function import CompiledFunction
from codablellm.core.utils import PathLike

DECOMPILER: Final[Dict[str, str]] = {}


class Decompiler(ABC):

    @abstractmethod
    def decompile(self, path: PathLike) -> Sequence[CompiledFunction]:
        pass


def get_decompiler(language: str) -> Decompiler:
    if language in DECOMPILER:
        module_path, class_name = DECOMPILER[language].rsplit('.', 1)
        module = importlib.import_module(module_path)
        return getattr(module, class_name)()
    raise ValueError(f'Unsupported language: {language}')
