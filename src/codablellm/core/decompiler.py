import importlib

from abc import ABC, abstractmethod
from typing import Dict, Final, TypedDict, Sequence
from codablellm.core.function import CompiledFunction
from codablellm.core.utils import PathLike


class NamedDecompiler(TypedDict):
    name: str
    class_import: str


DECOMPILER: Final[NamedDecompiler] = {
    'name': 'Ghidra',
    'class_import': 'codablellm.decompilers.ghidra.Ghidra'
}


class Decompiler(ABC):

    @abstractmethod
    def decompile(self, path: PathLike) -> Sequence[CompiledFunction]:
        pass


def get_decompiler() -> Decompiler:
    module_path, class_name = DECOMPILER['class_import'].rsplit('.', 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)()


def decompile(path: PathLike) -> Sequence[CompiledFunction]:
    return get_decompiler().decompile(path)
