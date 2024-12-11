
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class Subroutine:
    uid: str
    path: Path


@dataclass(frozen=True)
class SourceFunction(Subroutine):
    language: str
    definition: str
    name: str
    start_byte: int
    end_byte: int

    def with_definition(self, definition: str, name: Optional[str] = None,
                        write_back: bool = True) -> 'SourceFunction':
        source_function = SourceFunction(f'{self.path}:{name}' if name else self.uid, self.path,
                                         self.language,
                                         definition, name if name else self.name, self.start_byte,
                                         self.start_byte + len(definition))
        if write_back:
            source_code = source_function.path.read_text()
            source_function.path.write_text(source_code[:self.start_byte] +
                                            source_function.definition +
                                            source_code[self.end_byte:])
        return source_function

    @classmethod
    def from_source(cls, path: Path, language: str, definition: str, name: str, start_byte: int,
                    end_byte: int) -> 'SourceFunction':
        return cls(f'{path}:{name}', path, language, definition, name, start_byte, end_byte)


@dataclass(frozen=True)
class DecompiledFunction(Subroutine):
    definition: str
    name: str
    assembly: str
    architecture: str
