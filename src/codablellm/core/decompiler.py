import importlib

from abc import ABC, abstractmethod
from typing import Dict, Final, TypedDict, Sequence
from codablellm.core.function import DecompiledFunction
from codablellm.core.utils import PathLike


class NamedDecompiler(TypedDict):
    name: str
    class_path: str


DECOMPILER: Final[NamedDecompiler] = {
    'name': 'Ghidra',
    'class_path': 'codablellm.decompilers.ghidra.Ghidra'
}


class Decompiler(ABC):

    @abstractmethod
    def decompile(self, path: PathLike) -> Sequence[DecompiledFunction]:
        pass


def get_decompiler() -> Decompiler:
    module_path, class_name = DECOMPILER['class_path'].rsplit('.', 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)()


def decompile(path: PathLike) -> Sequence[DecompiledFunction]:
    return get_decompiler().decompile(path)
