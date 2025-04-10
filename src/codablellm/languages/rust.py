from pathlib import Path
from typing import Final, Optional, Sequence, Set

import tree_sitter_rust as tsr
from tree_sitter import Language

from codablellm.core.function import SourceFunction
from codablellm.core.utils import PathLike
from codablellm.languages.common import TreeSitterExtractor, rglob_file_extensions

TREE_SITTER_QUERY: Final[str] = (
    ";; Top-level function definitions"
    "(function_item"
    "  name: (identifier) @function.name) @function.definition"
    ""
    ";; Method definitions inside impl blocks"
    "(impl_item"
    "  type: (type_identifier) @class.name"
    "  body: (declaration_list"
    "    (function_item"
    "      name: (identifier) @function.name) @function.definition))"
)
"""
Tree-sitter query for extracting function names and definitions.
"""


class RustExtractor(TreeSitterExtractor):
    """
    Source code extractor for extracting JavaScript functions.
    """

    def __init__(self) -> None:
        super().__init__("Rust", Language(tsr.language()), TREE_SITTER_QUERY)

    def extract(
        self, file_path: PathLike, repo_path: Optional[PathLike] = None
    ) -> Sequence[SourceFunction]:
        return super().extract(file_path, repo_path)

    def get_extractable_files(self, path: Path | str) -> Set[Path]:
        return rglob_file_extensions(path, [".rs", ".rlib"])
