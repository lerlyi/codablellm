"""
Module containing functions for decompiling binaries.

This module manages decompiler registration and configuration, allowing `codablellm`
to use different backends for binary decompilation.
"""

import logging
import subprocess
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import (
    Any,
    Dict,
    Final,
    List,
    Literal,
    Mapping,
    NamedTuple,
    Optional,
    Sequence,
    Type,
)

from prefect import flow, task
from tree_sitter import Node

from codablellm.core.function import DecompiledFunction
from codablellm.core.utils import (
    ASTEditor,
    DynamicSymbol,
    PathLike,
    benchmark_task,
    dynamic_import,
    is_binary,
)
from codablellm.languages.c import CExtractor

logger = logging.getLogger(__name__)


class RegisteredDecompiler(NamedTuple):
    name: str
    symbol: DynamicSymbol


_decompiler: RegisteredDecompiler = RegisteredDecompiler(
    "Ghidra", (Path(__file__).parent.parent / "decompilers" / "ghidra.py", "Ghidra")
)


def set(name: str, file: PathLike, class_name: str) -> None:
    """
    Sets the decompiler used by `codablellm`.

    Parameters:
        class_path:  The fully qualified class path (in the form `module.submodule.ClassName`) of the subclass of `Decompiler` to use.
    """
    global _decompiler
    old_decompiler = _decompiler
    _decompiler = RegisteredDecompiler(name, (Path(file), class_name))
    # Instantiate decompiler to ensure it can be properly imported
    try:
        create_decompiler()
    except:
        logger.error(f"Could not create {repr(name)} extractor")
        _decompiler = old_decompiler
        raise
    logger.info(f"Using {repr(name)} ({file}::{class_name}) as the decompiler")


def get() -> RegisteredDecompiler:
    return _decompiler


GET_C_SYMBOLS_QUERY: Final[str] = (
    "(function_definition"
    "    declarator: (function_declarator"
    "        declarator: (identifier) @function.symbols"
    "    )"
    ")"
    "(call_expression"
    "    function: (identifier) @function.symbols"
    ")"
)
"""
Tree-sitter query used to extract all C symbols from a function definition.
"""


def pseudo_strip(
    decompiler: "Decompiler", function: DecompiledFunction
) -> "DecompiledFunction":
    """
    Creates a stripped version of the decompiled function with anonymized symbol names.

    This method replaces all function symbols in both the function definition and assembly code
    with generated placeholders (e.g., `FUN_<addr>` or `sub_<addr>`), ensuring sensitive or original
    identifiers are removed. The resulting `DecompiledFunction` has an updated definition,
    stripped function name, and modified assembly code.

    Returns:
        A new `DecompiledFunction` instance with stripped symbols and updated assembly.
    """
    definition = function.definition
    assembly = function.assembly
    symbol_mapping: Dict[str, str] = {}

    def anonymize_symbol(node: Node) -> str:
        nonlocal symbol_mapping, assembly
        if not node.text:
            raise ValueError(f"Expected all function.symbols to have text: {node}")
        orig_function = node.text.decode()
        stripped_symbol = symbol_mapping.setdefault(
            orig_function, decompiler.get_stripped_function_name(function.address)
        )
        assembly = assembly.replace(orig_function, stripped_symbol)
        return stripped_symbol

    editor = ASTEditor(CExtractor.PARSER, definition)
    editor.match_and_edit(GET_C_SYMBOLS_QUERY, {"function.symbols": anonymize_symbol})
    definition = editor.source_code

    first_function = next(iter(symbol_mapping.values()), function.name)

    return DecompiledFunction(
        uid=function.uid,
        path=function.path,
        name=first_function,
        definition=definition,
        assembly=assembly,
        architecture=function.architecture,
        address=function.address,
    )


class Decompiler(ABC):
    """
    Abstract base class for a decompiler that extracts decompiled functions from compiled binaries.
    """

    @abstractmethod
    def decompile(self, path: PathLike) -> Sequence[DecompiledFunction]:
        """
        Decompiles a binary and retrieves all decompiled functions contained in it.

        Parameters:
            path: The path to the binary file to be decompiled.

        Returns:
            A sequence of `DecompiledFunction` objects representing the functions extracted from the binary.
        """
        pass

    @abstractmethod
    def get_stripped_function_name(self, address: int) -> str:
        pass

    def decompile_stripped(
        self, path: PathLike, strategy: "SymbolRemovalStrategy"
    ) -> Sequence[DecompiledFunction]:
        logger.info(f"Stripping {repr(path)}...")
        if strategy == "strip":
            logger.debug(f"Decompiling {repr(path)} with symbols (pre-strip)...")
            debug_functions = self.decompile(path)

            logger.debug(f"Running `strip` on {repr(path)}...")
            subprocess.run(
                ["strip", str(path)], capture_output=True, text=True, check=True
            )

            logger.debug(f"Decompiling {repr(path)} without symbols (post-strip)...")
            stripped_functions = self.decompile(path)
            stripped_by_addr = {f.address: f for f in stripped_functions}

            # Merge stripped data into metadata of original functions
            combined: List[DecompiledFunction] = []
            for func in debug_functions:
                stripped = stripped_by_addr.get(func.address)
                if stripped:
                    new_metadata = {
                        **func.metadata,
                        "stripped_definition": stripped.definition,
                        "stripped_assembly": stripped.assembly,
                    }
                    combined.append(replace(func, _metadata=new_metadata))
                else:
                    logger.warning(
                        f"No stripped definition found for {func.name} @ {hex(func.address)}"
                    )
                    combined.append(func)  # Fall back to original

            return combined
        logger.debug(f"Utilizing pseudo-strip strategy for {repr(path)}")
        return [pseudo_strip(self, function) for function in self.decompile(path)]
        # strip, decompile again, and return the stripped functions


def create_decompiler(*args: Any, **kwargs: Any) -> Decompiler:
    """
    Initializes an instance of the decompiler that is being used by `codablellm`.

    Parameters:
        args:  Positional arguments to pass to the decompiler's `__init__` method.
        kwargs:  Keyword arguments to pass to the decompiler's `__init__` method.

    Returns:
        An instance of the specified `Decompiler` subclass.

    Raises:
        DecompilerNotFound: If the specified decompiler cannot be imported or if the class cannot be found in the specified module.
    """
    file, symbol = _decompiler.symbol
    decompiler_class: Type[Decompiler] = dynamic_import(file, symbol)
    return decompiler_class(*args, **kwargs)


SymbolRemovalStrategy = Literal["strip", "pseudo-strip"]


@dataclass(frozen=True)
class DecompileConfig:
    """
    Configuration for decompiling binaries.
    """

    max_workers: Optional[int] = None
    """
    Maximum number of binaries to decompile in parallel.
    """
    decompiler_args: Sequence[Any] = field(default_factory=list)
    """
    Positional arguments to pass to the decompiler's `__init__` method.
    """
    decompiler_kwargs: Mapping[str, Any] = field(default_factory=dict)
    """
    Keyword arguments to pass to the decompiler's `__init__` method.
    """
    symbol_remover: Optional[SymbolRemovalStrategy] = None
    recursive: bool = False
    strict: bool = False

    def __post_init__(self) -> None:
        if self.max_workers and self.max_workers < 1:
            raise ValueError("Max workers must be a positive integer")


@task(name="decompile", on_completion=[benchmark_task])
def decompile_task(
    *paths: PathLike, config: DecompileConfig
) -> List[DecompiledFunction]:
    """
    Decompiles binaries and extracts decompiled functions from the given path or list of paths.

    Parameters:
        paths: A single path or sequence of paths pointing to binary files or directories containing binaries.
        config: Decompilation configuration options.
        as_callable_pool: If `True`, returns a callable pool for deferred execution, typically used for progress bar handling or asynchronous processing.

    Returns:
        Either a list of `DecompiledFunction` instances or a `_CallableDecompiler` for deferred execution.
    """
    bins: List[Path] = []
    # Collect binary files
    for path in paths:
        path = Path(path)
        try:
            path.mkdir(parents=True, exist_ok=True)
        except FileExistsError:
            # In case the path is not a directory, continue
            pass
        # If a path is a directory, glob all child binaries
        glob = path.rglob if config.recursive else path.glob
        bins.extend([b for b in glob("*") if is_binary(b)] if path.is_dir() else [path])
    if not any(bins):
        logger.warning("No binaries found to decompile")
    # Create decompiler
    decompiler = create_decompiler(*config.decompiler_args, **config.decompiler_kwargs)
    # Submit decompile tasks
    logger.info(f"Submitting {get().name} decompile tasks...")
    if config.symbol_remover:
        futures = [
            task(decompiler.decompile_stripped, on_failure=[benchmark_task]).submit(
                bin, config.symbol_remover, return_state=True
            )
            for bin in bins
        ]
    else:
        futures = [
            task(decompiler.decompile, on_failure=[benchmark_task]).submit(bin, return_state=True) for bin in bins
        ]
    results = [future.result(raise_on_failure=config.strict) for future in futures]
    functions: List[DecompiledFunction] = []
    for result in results:
        if isinstance(result, list):
            functions.extend(result)
    logger.info(f"Successfully decompiled {len(functions)} functions")
    return functions


@flow
def decompile(*paths: PathLike, config: DecompileConfig) -> List[DecompiledFunction]:
    return decompile_task(*paths, config=config)
