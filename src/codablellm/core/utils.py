from pathlib import Path
from typing import Union


PathLike = Union[Path, str]


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