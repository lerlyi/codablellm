import importlib

from abc import ABC, abstractmethod
from typing import Any, Dict, Final, TypedDict, Sequence
from codablellm.core.function import DecompiledFunction
from codablellm.core.utils import PathLike


class NamedDecompiler(TypedDict):
    name: str
    class_path: str


DECOMPILER: Final[NamedDecompiler] = {
    'name': 'Ghidra',
    'class_path': 'codablellm.decompilers.ghidra.Ghidra'
}


def set_decompiler(name: str, class_path: str) -> None:
    DECOMPILER['name'] = name
    DECOMPILER['class_path'] = class_path


class Decompiler(ABC):

    @abstractmethod
    def decompile(self, path: PathLike) -> Sequence[DecompiledFunction]:
        pass


def get_decompiler(*args: Any, **kwargs: Any) -> Decompiler:
    module_path, class_name = DECOMPILER['class_path'].rsplit('.', 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)(*args, **kwargs)


def decompile(path: PathLike, *args: Any, **kwargs: Any) -> Sequence[DecompiledFunction]:
    return get_decompiler(*args, **kwargs).decompile(path)
