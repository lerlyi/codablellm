"""
Generate the code documentation pages and navigation.
"""

from typing import Final
import mkdocs_gen_files

from pathlib import Path
from mkdocs_gen_files.nav import Nav

README_PATH: Final[Path] = Path(__file__).parent.parent / 'README.md'

# Create About page as the index file for the documentation
with mkdocs_gen_files.open("index.md", "w") as nav_file:
    lines = [
        '# About',
        *README_PATH.read_text().splitlines()
    ]
    nav_file.write('\n'.join(lines))
