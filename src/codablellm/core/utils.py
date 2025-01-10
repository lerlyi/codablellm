from functools import wraps
import importlib
import json
import logging
import os
from pathlib import Path
from queue import Queue
import tempfile
from typing import (Any, Callable, Dict, Generator, Iterable, List, Optional, Protocol, Set,
                    Type, TypeVar, Union)

from tree_sitter import Node, Parser

from codablellm.exceptions import ExtraNotInstalled, TSParsingError

logger = logging.getLogger('codablellm')

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
            raise TSParsingError('Parsing error while editing code')

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


def requires_extra(extra: str, feature: str, module: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                importlib.import_module(module)
            except ImportError as e:
                raise ExtraNotInstalled(f'{feature} requires the "{extra}" extra to be installed. '
                                        f'Install with "pip install codablellm[{extra}]"') from e
            return func(*args, **kwargs)
        return wrapper
    return decorator


T = TypeVar('T')


def iter_queue(queue: Queue[T]) -> Generator[T, None, None]:
    while not queue.empty():
        yield queue.get()


def get_checkpoint_file(prefix: str) -> Path:
    return Path(tempfile.gettempdir()) / f'{prefix}_{os.getpid()}.json'


def get_checkpoint_files(prefix: str) -> List[Path]:
    return list(Path(tempfile.gettempdir()).glob(f'{prefix}_*'))


def save_checkpoint_file(prefix: str, contents: Iterable[SupportsJSON]) -> None:
    checkpoint_file = get_checkpoint_file(prefix)
    checkpoint_file.write_text(json.dumps([c.to_json() for c in contents]))


def load_checkpoint_data(prefix: str, delete_on_load: bool = False) -> List[SupportsJSON_T]:
    checkpoint_data: List[SupportsJSON_T] = []
    checkpoint_files = get_checkpoint_files(prefix)
    for checkpoint_file in checkpoint_files:
        logger.debug(f'Loading checkpoint data from "{checkpoint_file.name}"')
        checkpoint_data.extend(json.loads(checkpoint_file.read_text()))
        if delete_on_load:
            logger.debug(f'Removing checkpoint file "{checkpoint_file.name}"')
            checkpoint_file.unlink(missing_ok=True)
    return checkpoint_data
