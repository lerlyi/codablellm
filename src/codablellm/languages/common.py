from abc import abstractmethod
import itertools
from pathlib import Path
from typing import List, Optional, Sequence, Set

from tree_sitter import Language, Parser

from codablellm.core.extractor import Extractor
from codablellm.core.function import SourceFunction
from codablellm.core.utils import PathLike


class TreeSitterExtractor(Extractor):

    def __init__(self, name: str, query: str) -> None:
        self.name = name
        self._query = query

    def extract(
        self, file_path: PathLike, repo_path: Optional[PathLike] = None
    ) -> Sequence[SourceFunction]:
        functions = []
        file_path = Path(file_path)
        if repo_path is not None:
            repo_path = Path(repo_path)
        language = self.get_language()
        ast = Parser(language).parse(file_path.read_bytes())
        for _, group in language.query(self._query).matches(ast.root_node):
            (function_definition,) = group["function.definition"]
            (function_name,) = group["function.name"]
            (class_name,) = group.get("class.name", [None])
            if not function_definition.text or not function_name.text:
                raise ValueError(
                    "Expected function.name and function.definition to have text"
                )
            if class_name:
                if not class_name.text:
                    raise ValueError("Expected class.name to have text")
                class_name_text = class_name.text
            else:
                class_name_text = None
            functions.append(
                SourceFunction.from_source(
                    file_path,
                    self.name,
                    function_definition.text.decode(),
                    function_name.text.decode(),
                    function_definition.start_byte,
                    function_definition.end_byte,
                    repo_path=repo_path,
                    class_name=class_name_text.decode() if class_name_text else None,
                )
            )
        return functions

    @abstractmethod
    def get_language(self) -> Language:
        pass


def rglob_file_extensions(path: PathLike, extensions: List[str]) -> Set[Path]:
    path = Path(path)
    if any(path.suffix.casefold() == e.casefold() for e in extensions):
        return {path}
    return set(
        itertools.chain.from_iterable(
            [path.rglob(f"*{e}", case_sensitive=False) for e in extensions]
        )
    )
