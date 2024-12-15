from ast import TypeVar
from pathlib import Path
from typing import Any, Dict, Generic, List, Optional, Protocol, Type, Union


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
