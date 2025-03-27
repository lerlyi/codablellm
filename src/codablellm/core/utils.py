'''
Core utility functions for codablellm.
'''

from contextlib import AbstractContextManager, contextmanager, nullcontext
from itertools import dropwhile, takewhile
import subprocess
import time
from functools import wraps
import importlib
import json
import logging
import os
from pathlib import Path
from queue import Queue
import tempfile
from typing import (Any, Callable, Dict, Generator, Iterable, List, Literal, Optional, Protocol, Sequence, Set, Tuple,
                    Type, TypeVar, Union, overload)

from rich import print
from rich.prompt import Prompt
from tree_sitter import Node, Parser

from codablellm.exceptions import ExtraNotInstalled, TSParsingError

logger = logging.getLogger('codablellm')

PathLike = Union[Path, str]
'''
An object representing a file system path.
'''

JSONValue = Optional[Union[str, int, float,
                           bool, List['JSONValue'], 'JSONObject']]
'''
Represents a valid JSON value
'''
JSONObject = Dict[str, JSONValue]
'''
Represents a JSON object.
'''

JSONObject_T = TypeVar('JSONObject_T', bound=JSONObject)
SupportsJSON_T = TypeVar('SupportsJSON_T',
                         bound='SupportsJSON')


class SupportsJSON(Protocol):
    '''
    A class that supports JSON serialization/deserialization.
    '''

    def to_json(self) -> JSONObject_T:  # type: ignore
        '''
        Serializes this object to a JSON object.

        Returns:
            A JSON representation of the object.
        '''
        ...

    @classmethod
    def from_json(cls: Type[SupportsJSON_T], json_obj: JSONObject_T) -> SupportsJSON_T:  # type: ignore
        '''
        Deserializes a JSON object to this object.

        Parameters:
            json_obj: The JSON representation of this object.

        Returns:
            This object loaded from the JSON object.
        '''
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
    '''
    Filters out keyword arguments with `None` values.

    Returns a dictionary containing only key-value pairs where the value is not `None`.

    Parameters:
        **kwargs: Arbitrary keyword arguments.

    Returns:
        A dictionary of keyword arguments with `None` values removed.
    '''
    return {k: v for k, v in kwargs.items() if v is not None}


class ASTEditor:
    '''
    A Tree-sitter AST editor.
    '''

    def __init__(self, parser: Parser, source_code: str, ensure_parsable: bool = True) -> None:
        '''
        Initializes the AST editor with a parser and source code.

        Parameters:
            parser: The `Parser` object used to parse the source code.
            source_code: The source code to be edited.
            ensure_parsable: If `True`, raises an error if edits result in an invalid AST.
        '''
        self.parser = parser
        self.source_code = source_code
        self.ast = self.parser.parse(source_code.encode())
        self.ensure_parsable = ensure_parsable

    def edit_code(self, node: Node, new_code: str) -> None:
        '''
        Edits the source code at the specified AST node and updates the AST.

        Parameters:
            node: The `Node` object representing the code to replace.
            new_code: The new code to insert in place of the node's source code.

        Raises:
            TSParsingError: If `ensure_parsable` is `True` and the resulting AST has parsing errors.
        '''
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
        '''
        Searches the AST using a Tree-sitter query and applies code edits to matching nodes.

        For each match group, replaces the matched node's code with a provided string or the
        result of a callable that returns the replacement string.

        Parameters:
            query: The Tree-sitter query string to use for finding matching nodes.
            groups_and_replacement: A mapping from query group names to either replacement strings
                                    or callables that take a `Node` and return a replacement string.

        Raises:
            TSParsingError: If an edit introduces parsing errors and `ensure_parsable` is `True`.
        '''
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
    '''
    Decorator that enforces the presence of an optional dependency (extra) before executing a function.

    If the required module is not installed, raises an `ExtraNotInstalled` error with instructions
    on how to install the missing extra.

    Parameters:
        extra: The name of the extra (e.g., "excel") required for the feature.
        feature: A description of the feature that requires the extra.
        module: The module name to attempt to import.

    Returns:
        A decorator that checks for the required extra before calling the function.

    Raises:
        ExtraNotInstalled: If the required module is not installed.
    '''

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
    '''
    Iterates over all items in a queue until it is empty.

    Parameters:
        queue: A `Queue` object containing items to iterate over.

    Returns:
        A generator that yields each item from the queue.
    '''
    while not queue.empty():
        yield queue.get()


def get_checkpoint_file(prefix: str) -> Path:
    '''
    Returns the checkpoint file path for the current process based on the given prefix.

    The checkpoint file is stored in the system temporary directory and named using
    the format: `{prefix}_{pid}.json`.

    Parameters:
        prefix: The filename prefix for the checkpoint file.

    Returns:
        A `Path` object pointing to the checkpoint file.
    '''
    return Path(tempfile.gettempdir()) / f'{prefix}_{os.getpid()}.json'


def get_checkpoint_files(prefix: str) -> List[Path]:
    '''
    Retrieves all checkpoint files matching the given prefix.

    Parameters:
        prefix: The filename prefix used to locate checkpoint files.

    Returns:
        A list of `Path` objects for all matching checkpoint files.
    '''
    return list(Path(tempfile.gettempdir()).glob(f'{prefix}_*'))


def save_checkpoint_file(prefix: str, contents: Iterable[SupportsJSON]) -> None:
    '''
    Saves checkpoint data to a file based on the given prefix.

    The contents are converted to JSON and written to a checkpoint file named
    `{prefix}_{pid}.json` in the system temporary directory.

    Parameters:
        prefix: The filename prefix for the checkpoint file.
        contents: An iterable of objects that support JSON serialization via `to_json()`.
    '''
    checkpoint_file = get_checkpoint_file(prefix)
    checkpoint_file.write_text(json.dumps([c.to_json() for c in contents]))


def load_checkpoint_data(prefix: str, delete_on_load: bool = False) -> List[JSONObject]:
    '''
    Loads checkpoint data from all checkpoint files matching the given prefix.

    The function reads and aggregates JSON data from each checkpoint file and optionally
    deletes the checkpoint files after loading.

    Parameters:
        prefix: The filename prefix used to locate checkpoint files.
        delete_on_load: If `True`, deletes the checkpoint files after loading their contents.

    Returns:
        A list of JSON objects aggregated from all matching checkpoint files.
    '''
    checkpoint_data: List[JSONObject] = []
    checkpoint_files = get_checkpoint_files(prefix)
    for checkpoint_file in checkpoint_files:
        logger.debug(f'Loading checkpoint data from "{checkpoint_file.name}"')
        checkpoint_data.extend(json.loads(checkpoint_file.read_text()))
        if delete_on_load:
            logger.debug(f'Removing checkpoint file "{checkpoint_file.name}"')
            checkpoint_file.unlink(missing_ok=True)
    return checkpoint_data


def benchmark_function(task: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    '''
    Decorator that benchmarks the execution time of a function and logs the duration.

    Parameters:
        task: Description of the task being benchmarked.

    Returns:
        A decorator that wraps the function and logs the execution time in seconds
    '''
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            result = func(*args, **kwargs)
            end = time.perf_counter()
            logger.info(f'{task} took {end - start:.2f} seconds')
            return result
        return wrapper
    return decorator


@contextmanager
def benchmark_context(task: str) -> Generator[None, None, None]:
    '''
    Context manager that benchmarks the execution time of a code block and logs the duration.

    Parameters:
        task: Description of the task being benchmarked.
    '''
    start = time.perf_counter()
    yield
    end = time.perf_counter()
    logger.info(f'{task} took {end - start:.2f} seconds')


Command = Union[Sequence[str]]
'''
A CLI command.
'''

CommandErrorHandler = Literal['interactive', 'ignore', 'none']
'''
Defines the strategies for handling errors encountered during the execution of a CLI command.

Supported Error Handlers:
    - **`ignore`**: The CLI command error is ignored, and execution continues without interruption.
    - **`none`**: An exception is raised immediately upon encountering the CLI error.
    - **`interactive`**: The user is prompted to resolve the error manually, allowing for
    interactive handling of the issue.
'''


def add_command_args(command: Command, *args: Any) -> Command:
    '''
    Appends additional arguments to a CLI command.

    Parameters:
        command: The CLI command to append.
        args: Additional arguments to append to the command.

    Returns:
        The updated command with the appended arguments.
    '''
    command = [command] if isinstance(command, str) else command
    return [*command, *args]


def execute_command(command: Command, error_handler: CommandErrorHandler = 'none',
                    task: Optional[str] = None, ctx: AbstractContextManager[Any] = nullcontext(),
                    log_level: Literal['debug', 'info'] = 'info',
                    print_errors: bool = True, cwd: Optional[PathLike] = None) -> str:
    '''
    Executes a CLI command.

    Parameters:
        command: The CLI command to be executed.
        error_handler: Specifies how to handle errors during command execution.
        task: An optional description of the task being performed used for logging.
        ctx: Context manager to use for the command execution.
        log_level: The logging level for the task description.
        print_errors: If `True`, prints the error output to the console.
        cwd: The working directory to execute the command in.

    Returns:
        The output of the command.

    Raises:
        CalledProcessError: If the command fails and the error handler is set to 'none'.
    '''
    command_str = command if isinstance(command, str) \
        else ' '.join(str(c) for c in command)
    log_task = logger.debug if log_level == 'debug' else logger.info
    if not task:
        task = f'Executing: "{command_str}"'
    if task:
        log_task(task)
    output = ''
    try:
        with ctx:
            output = subprocess.check_output(command_str, shell=True, text=True,
                                             cwd=cwd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        output = e.output
        logger.error(f'Command failed: "{command_str}"')
        if print_errors:
            print(f'[red][b]Command failed: "{command_str}"[/b]'
                  f'\nOutput: {output}')
        if error_handler == 'interactive':
            result = Prompt.ask('A command error occurred. You can manually fix the issue and '
                                'retry, ignore the error to continue, abort the process, or edit '
                                'the command. How would you like to proceed?',
                                choices=['retry', 'ignore', 'abort', 'edit'],
                                case_sensitive=False, default='retry')
            if result == 'retry':
                execute_command(command, error_handler=error_handler,
                                task=task)
            elif result == 'abort':
                error_handler = 'none'
            elif result == 'edit':
                edited_command = Prompt.ask('Enter the new command to execute',
                                            default=f'"{command_str}"').strip('"\'')
                execute_command(edited_command, error_handler=error_handler,
                                task=task)
        if error_handler == 'none':
            raise
    else:
        log_task(f'Successfully executed "{command_str}"')
    finally:
        if output:
            logger.debug(f'"{command_str}" output:\n"{output}"')
    return output
