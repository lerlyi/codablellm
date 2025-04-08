from typing import List, Sequence

try:
    from angr import Project
except ModuleNotFoundError:
    Project = None
from codablellm.core.decompiler import Decompiler
from codablellm.core.function import DecompiledFunction
from codablellm.core.utils import PathLike, requires_extra


def is_installed() -> bool:
    return Project is not None


class Angr(Decompiler):

    @requires_extra("angr", "Angr Decompiler", "angr")
    def decompile(self, path: PathLike) -> Sequence[DecompiledFunction]:
        # Load the binary
        project = Project(path, load_options={"auto_load_libs": False})  # type: ignore
        # Get architecture name
        architecture = project.arch.name

        # Result list
        result_list: List[DecompiledFunction] = []

        # Iterate over functions using CFG
        cfg = project.analyses.CFGFast(normalize=True)

        for func_addr, function in cfg.kb.functions.items():
            # Function name
            name = function.name
            address = func_addr

            # Get assembly using Capstone
            block = project.factory.block(func_addr)
            assembly = block.capstone.pretty_print()

            # Get "definition" via VEX IR (pseudo-C is not supported)
            vex_ir = "\n".join(str(stmt) for stmt in block.vex.statements)

            func_dict = {
                "path": path,
                "definition": vex_ir,
                "name": name,
                "assembly": assembly,
                "architecture": architecture,
                "address": address,
            }
            result_list.append(DecompiledFunction.from_decompiled_json(func_dict))
        return result_list
