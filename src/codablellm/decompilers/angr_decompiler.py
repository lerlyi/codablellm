import logging
from typing import List, Sequence

try:
    from angr import Project
except ModuleNotFoundError:
    Project = None
from codablellm.core.decompiler import Decompiler
from codablellm.core.function import DecompiledFunction
from codablellm.core.utils import PathLike, requires_extra

logger = logging.getLogger(__name__)


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
            assembly = []
            for block in function.blocks:
                for insn in block.capstone.insns:
                    assembly.append(f"{insn.mnemonic} {insn.op_str}".strip())

            assembly_str = "\n".join(assembly)

            # Decompile the main function
            decompilation = project.analyses.Decompiler(function)
            if not decompilation.codegen:
                raise ValueError(f"Angr decompilation failed: {repr(name)}")
            definition = decompilation.codegen.text
            logger.debug(f"Successfully decompiled {repr(name)}")
            func_dict = {
                "path": str(path),
                "definition": definition,
                "name": name,
                "assembly": assembly_str,
                "architecture": architecture,
                "address": address,
            }
            result_list.append(DecompiledFunction.from_decompiled_json(func_dict))
        return result_list

    def get_stripped_function_name(self, address: int) -> str:
        return f"sub_{address:X}"
