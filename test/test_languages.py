from calendar import c
from pathlib import Path
from codablellm.core.function import SourceFunction
from codablellm.languages import *


def test_c_extraction(tmp_path: Path) -> None:
    c_file = tmp_path / 'main.c'
    c_definition = (
        'int main(int argc, char **argv) {'
        '\n\tprintf("Hello, world!");'
        '\n\treturn 0;'
        '\n}')
    c_code = ('#include <stdio.h>'
              '\n'
              f'\n{c_definition}'
              '\n')
    c_file.write_text(c_code)
    functions = CExtractor().extract(c_file)
    assert len(functions) == 1
    function, = functions
    assert function.name == 'main'
    assert function.language == 'C'
    assert function.definition.splitlines() == c_definition.splitlines()
    assert function.path == c_file
    assert function.uid == f'{c_file.name}::main'
