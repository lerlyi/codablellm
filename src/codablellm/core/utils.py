from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Set, Type, TypeVar, Union

from tree_sitter import Node, Parser, Tree

PathLike = Union[Path, str]
JSONValue = Optional[Union[str, int, float,
                           bool, List['JSONValue'], 'JSONObject']]
JSONObject = Dict[str, JSONValue]

JSONObject_T = TypeVar('JSONObject_T', bound=JSONObject)  # type: ignore
SupportsJSON_T = TypeVar('SupportsJSON_T',
                         bound='SupportsJSON')  # type: ignore


class SupportsJSON(Protocol):

    def to_json(self) -> JSONObject_T:  # type: ignore
        ...

    @classmethod
    def from_json(cls: Type[SupportsJSON_T], json_obj: JSONObject_T) -> SupportsJSON_T:  # type: ignore
        ...


def get_readable_file_size(size: int) -> str:
    '''
    Converts number of bytes to a human readable output (i.e. bytes, KB, MB, GB, TB.)

    Parameters:
        size: The number of bytes.

    Returns:
        A human readable output of the number of bytes.
    '''
    kb = round(size / 2 ** 10, 3)
    mb = round(size / 2 ** 20, 3)
    gb = round(size / 2 ** 30, 3)
    tb = round(size / 2 ** 40, 3)

    for measurement, suffix in [(tb, 'TB'), (gb, 'GB'), (mb, 'MB'), (kb, 'KB')]:
        if measurement >= 1:
            return f'{measurement} {suffix}'
    return f'{size} bytes'


def is_binary(file_path: PathLike) -> bool:
    '''
    Checks if a file is a binary file.

    Parameters:
        file_path: Path to a potential binary file.

    Returns:
        True if the file is a binary.
    '''
    file_path = Path(file_path)
    if file_path.is_file():
        with open(file_path, 'rb') as file:
            # Read the first 1KB of the file and check for a null byte or non-printable characters
            chunk = file.read(1024)
            return b'\0' in chunk or any(byte > 127 for byte in chunk)
    return False


def resolve_kwargs(**kwargs: Any) -> Dict[str, Any]:
    return {k: v for k, v in kwargs.items() if v is not None}


def replace_code(parser: Parser, ast: Tree, node: Node, new_code: str) -> Tree:
    if not ast.root_node.text:
        raise ValueError('Expected AST to have text')
    code = ast.root_node.text.decode()
    num_bytes = len(new_code)
    num_lines = new_code.count('\n')
    last_col_num_bytes = len(new_code.splitlines()[-1])
    code = code[:node.start_byte] + new_code + code[node.end_byte:]
    ast.edit(
        node.start_byte,
        node.end_byte,
        node.start_byte + num_bytes,
        node.start_point,
        node.end_point,
        (node.start_point.row + num_lines,
         node.start_point.column + last_col_num_bytes)
    )
    ast = parser.parse(code.encode(), old_tree=ast)
    return ast


class ASTEditor:

    def __init__(self, parser: Parser, source_code: str, ensure_parsable: bool = True) -> None:
        self.parser = parser
        self.source_code = source_code
        self.ast = self.parser.parse(source_code.encode())
        self.ensure_parsable = ensure_parsable

    def edit_code(self, node: Node, new_code: str) -> None:
        # Calculate new code metrics
        num_bytes = len(new_code)
        num_lines = new_code.count('\n')
        last_col_num_bytes = len(new_code.splitlines()[-1])
        # Update the source code with the new code
        self.source_code = (
            self.source_code[:node.start_byte] +
            new_code +
            self.source_code[node.end_byte:]
        )
        # Perform the AST edit
        self.ast.edit(
            start_byte=node.start_byte,
            old_end_byte=node.end_byte,
            new_end_byte=node.start_byte + num_bytes,
            start_point=node.start_point,
            old_end_point=node.end_point,
            new_end_point=(
                node.start_point.row + num_lines,
                node.start_point.column + last_col_num_bytes
            )
        )
        # Re-parse the updated source code
        self.ast = self.parser.parse(self.source_code.encode(),
                                     old_tree=self.ast)
        # Check for parsing errors if required
        if self.ensure_parsable and self.ast.root_node.has_error:
            raise ValueError('Parsing error while editing code')

    def match_and_edit(self, query: str,
                       groups_and_replacement: Dict[str, Union[str, Callable[[Node], str]]]) -> None:
        modified_nodes: Set[Node] = set()
        matches = self.ast.language.query(query).matches(self.ast.root_node)
        for idx in range(len(matches)):
            _, capture = matches.pop(idx)
            for group, replacement in groups_and_replacement.items():
                nodes = capture.get(group)
                if nodes:
                    node = nodes.pop()
                    if node not in modified_nodes:
                        if not isinstance(replacement, str):
                            replacement = replacement(node)
                        self.edit_code(node, replacement)
                        modified_nodes.add(node)
                        matches = self.ast.language.query(
                            query).matches(self.ast.root_node)
                        break
