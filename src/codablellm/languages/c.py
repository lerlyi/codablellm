"""
Functionality for extracting C source code functions.
"""

from pathlib import Path
from typing import Final, Optional, Sequence, Set

import tree_sitter_c as tsc
from tree_sitter import Language, Parser

from codablellm.core.extractor import Extractor
from codablellm.core.function import SourceFunction
from codablellm.core.utils import PathLike
from codablellm.languages.common import rglob_file_extensions

TREE_SITTER_QUERY: Final[str] = (
    "(function_definition"
    "   declarator: (function_declarator"
    "       declarator: (identifier) @function.name"
    "   )"
    ") @function.definition"
)
"""
Tree-sitter query for extracting function names and definitions.
"""


class CExtractor(Extractor):
    """
    Source code extractor for extracting C functions.
    """

    NAME: Final[str] = "C"
    """
    Name of the language that is being extracted.
    """
    LANGUAGE: Final[Language] = Language(tsc.language())
    """
    Tree-sitter `Language` instance for C.
    """
    PARSER: Final[Parser] = Parser(LANGUAGE)
    """
    Tree-sitter `Parser` instance for C.
    """

    def extract(
        self, file_path: PathLike, repo_path: Optional[PathLike] = None
    ) -> Sequence[SourceFunction]:
        functions = []
        file_path = Path(file_path)
        if repo_path is not None:
            repo_path = Path(repo_path)
        ast = CExtractor.PARSER.parse(file_path.read_bytes())
        for _, group in CExtractor.LANGUAGE.query(TREE_SITTER_QUERY).matches(
            ast.root_node
        ):
            (function_definition,) = group["function.definition"]
            (function_name,) = group["function.name"]
            if not function_definition.text or not function_name.text:
                raise ValueError(
                    "Expected function.name and function.definition to have " "text"
                )
            functions.append(
                SourceFunction.from_source(
                    file_path,
                    CExtractor.NAME,
                    function_definition.text.decode(),
                    function_name.text.decode(),
                    function_definition.start_byte,
                    function_definition.end_byte,
                    repo_path=repo_path,
                )
            )
        return functions

    def get_extractable_files(self, path: PathLike) -> Set[Path]:
        return rglob_file_extensions(path, [".c"])
