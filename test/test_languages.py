from pathlib import Path
from codablellm.core.function import SourceFunction
from codablellm.languages import *


def test_c_extraction(tmp_path: Path) -> None:
    c_file = tmp_path / 'main.c'
    c_code = ('#include <stdio.h>'
              '\n'
              '\nint main(int argc, char **argv) {'
              '\n\tprintf("Hello, world!");'
              '\n\treturn 0;'
              '\n}')
    c_file.write_text(c_code)
    assert SourceFunction.from_source(c_file, 'C', c_code, 'main',
                                      20, 92) in CExtractor().extract(c_file)
