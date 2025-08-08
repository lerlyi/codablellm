"""
Functionality for extracting source code functions in the C language.
"""

from pathlib import Path
from typing import Final, Optional, Sequence, Set

import tree_sitter_c as tsc
from tree_sitter import Language, Parser, Query, QueryCursor

from codablellm.core.extractor import Extractor
from codablellm.core.function import SourceFunction
from codablellm.core.utils import PathLike
from codablellm.languages.common import rglob_file_extensions

TREE_SITTER_QUERY: Final[str] = """
(function_definition
   declarator: (function_declarator
       declarator: (identifier) @function.name
   )
) @function.definition
"""
"""
Tree-sitter query to retrieve function names and definitions.
"""


class CExtractor(Extractor):
    """
    Source code extractor for extracting functions in C language.
    """

    NAME: Final[str] = "C"
    """
    The name of the language to be extracted.
    """
    LANGUAGE: Final[Language] = Language(tsc.language())
    """
    An instance of `Language` Tree-sitter for C.
    """
    PARSER: Final[Parser] = Parser(LANGUAGE)
    """
    An instance of `Parser` Tree-sitter for C.
    """

    def extract(
        self, file_path: PathLike, repo_path: Optional[PathLike] = None
    ) -> Sequence[SourceFunction]:
        functions = []
        file_path = Path(file_path)
        if repo_path is not None:
            repo_path = Path(repo_path)

        source_bytes = file_path.read_bytes()
        ast = CExtractor.PARSER.parse(source_bytes)
        query = CExtractor.LANGUAGE.query(TREE_SITTER_QUERY)


        cursor = QueryCursor(query)


        all_matches = cursor.matches(ast.root_node)

        for match in all_matches:
            captures = match[1]


            function_definition_list = captures.get("function.definition")
            function_name_list = captures.get("function.name")

            if function_definition_list and function_name_list:

                function_definition = function_definition_list[0]
                function_name = function_name_list[0]

                if not function_definition.text or not function_name.text:
                    raise ValueError(
                        "Ожидалось, что function.name и function.definition будут содержать текст"
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
