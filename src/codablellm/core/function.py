
from dataclasses import dataclass, field, fields
import logging
from pathlib import Path
from typing import Any, Dict, Final, Mapping, Optional, TypedDict, Union, no_type_check
import uuid

from tree_sitter import Node, Parser
from tree_sitter import Language, Parser
import tree_sitter_c as tsc

from codablellm.core.utils import ASTEditor, JSONObject, SupportsJSON

logger = logging.getLogger('codablellm')


class FunctionJSONObject(TypedDict):
    uid: str
    path: str
    name: str
    definition: str
    metadata: Dict[str, Any]


@dataclass(frozen=True)
class Function(SupportsJSON):
    uid: str
    path: Path
    name: str
    definition: str
    _metadata: Dict[str, Any] = field(default_factory=dict, init=False)

    @property
    def metadata(self) -> Mapping[str, Any]:
        return {k: v for k, v in self._metadata.items()}

    def set_metadata(self, metadata: Mapping[str, Any]) -> None:
        class_fields = {f.name for f in fields(self)}
        for key, value in metadata.items():
            if key in class_fields:
                raise KeyError(f'Cannot set metadata "{key}" '
                               'to an existing class field')
            self._metadata[key] = value

    def add_metadata(self, metadata: Mapping[str, Any]) -> None:
        return self.set_metadata({**metadata, **self._metadata})

    def remove_metadata(self, key: str) -> None:
        del self._metadata[key]

    def to_json(self) -> FunctionJSONObject:
        return {'uid': self.uid, 'path': str(self.path), 'definition': self.definition,
                'name': self.name, 'metadata': self._metadata}

    @staticmethod
    def create_uid(file_path: Path, name: str, repo_path: Optional[Path] = None) -> str:
        if repo_path:
            try:
                relative_file_path = repo_path.name / \
                    file_path.resolve().relative_to(repo_path.resolve())
                scope = '::'.join(relative_file_path.parts)
            except ValueError as e:
                raise ValueError(f'Path to "{file_path.name}" is not in the '
                                 f'"{repo_path.name}" repository.') from e
        else:
            scope = file_path.parts[-1]
        return f'{scope}::{name}'

    @staticmethod
    def get_function_name(uid: str) -> str:
        return uid.split('::')[-1]

    @classmethod
    def from_json(cls, json_obj: FunctionJSONObject) -> 'Function':
        function = cls(json_obj['uid'], Path(json_obj['path']), json_obj['name'],
                       json_obj['definition'])
        function.set_metadata(json_obj['metadata'])
        return function


class SourceFunctionJSONObject(FunctionJSONObject):
    language: str
    start_byte: int
    end_byte: int
    class_name: Optional[str]


@dataclass(frozen=True)
class SourceFunction(Function):
    language: str
    start_byte: int
    end_byte: int
    class_name: Optional[str] = None

    def __post_init__(self) -> None:
        if self.start_byte < 0:
            raise ValueError('Start byte must be a non-negative integer')
        if self.start_byte > self.end_byte:
            raise ValueError('Start byte must be less than end byte')

    @property
    def is_method(self) -> bool:
        return self.class_name is not None

    def with_definition(self, definition: str, name: Optional[str] = None,
                        write_back: bool = True, metadata: Mapping[str, Any] = {}) -> 'SourceFunction':
        if not name:
            name = self.name
            uid = self.uid
        else:
            uid = SourceFunction.create_uid(self.path, name,
                                            class_name=self.class_name)
            scope, _ = self.uid.rsplit('::', maxsplit=1)
            uid = f'{scope}::{uid}'
        source_function = SourceFunction(uid, self.path, name, definition,
                                         self.language,
                                         self.start_byte,
                                         self.start_byte + len(definition),
                                         class_name=self.class_name)
        source_function.set_metadata({**metadata, **self.metadata})
        if write_back:
            logger.debug('Writing back modified definition to '
                         f'{source_function.path.name}...')
            modified_code = source_function.path.read_text().replace(
                self.definition, definition)
            source_function.path.write_text(modified_code)
        return source_function

    def to_json(self) -> SourceFunctionJSONObject:
        function_json = super().to_json()
        return {'language': self.language, 'start_byte': self.start_byte,
                'end_byte': self.end_byte, 'class_name': self.class_name,
                **function_json}

    @staticmethod
    def create_uid(file_path: Path, name: str, repo_path: Optional[Path] = None,
                   class_name: Optional[str] = None) -> str:
        uid = Function.create_uid(file_path, name, repo_path=repo_path)
        if class_name:
            scope, function = uid.rsplit('::', maxsplit=1)
            uid = f'{scope}::{class_name}.{function}'
        return uid

    @staticmethod
    def get_function_name(uid: str) -> str:
        return Function.get_function_name(uid).split('.')[-1]

    @classmethod
    def from_json(cls, json_obj: SourceFunctionJSONObject) -> 'SourceFunction':
        function = cls(json_obj['uid'], Path(json_obj['path']), json_obj['name'],
                       json_obj['definition'], json_obj['language'], json_obj['start_byte'],
                       json_obj['end_byte'], json_obj['class_name'])
        function.set_metadata(json_obj['metadata'])
        return function

    @classmethod
    def from_source(cls, file_path: Path, language: str, definition: str, name: str,
                    start_byte: int, end_byte: int, class_name: Optional[str] = None,
                    repo_path: Optional[Path] = None,
                    metadata: Mapping[str, Any] = {}) -> 'SourceFunction':
        function = cls(SourceFunction.create_uid(file_path, name, repo_path=repo_path, class_name=class_name),
                       file_path, name, definition, language, start_byte, end_byte,
                       class_name=class_name)
        function.set_metadata(metadata)
        return function


class DecompiledFunctionJSONObject(FunctionJSONObject):
    assembly: str
    architecture: str


GET_C_SYMBOLS_QUERY: Final[str] = (
    '(function_definition'
    '    declarator: (function_declarator'
    '        declarator: (identifier) @function.symbols'
    '    )'
    ')'
    '(call_expression'
    '    function: (identifier) @function.symbols'
    ')'
)
C_PARSER: Final[Parser] = Parser(Language(tsc.language()))


@dataclass(frozen=True)
class DecompiledFunction(Function):
    assembly: str
    architecture: str

    def to_stripped(self) -> 'DecompiledFunction':
        definition = self.definition
        assembly = self.assembly
        symbol_mapping: Dict[str, str] = {}

        def strip(node: Node) -> str:
            nonlocal symbol_mapping, assembly
            if not node.text:
                raise ValueError('Expected all function.symbols to have '
                                 f'text: {node}')
            orig_function = node.text.decode()
            stripped_symbol = symbol_mapping.setdefault(orig_function,
                                                        f'sub_{str(uuid.uuid4()).split("-", maxsplit=1)[0]}')
            assembly = assembly.replace(orig_function, stripped_symbol)
            return stripped_symbol

        editor = ASTEditor(C_PARSER, definition)
        logger.debug(f'Stripping {self.name}...')
        editor.match_and_edit(GET_C_SYMBOLS_QUERY,
                              {'function.symbols': strip})
        definition = editor.source_code
        first_function, *_ = (f for f in symbol_mapping.values()
                              if f.startswith('sub_'))
        return DecompiledFunction(self.uid, self.path, definition, first_function, assembly,
                                  self.architecture)

    def to_json(self) -> DecompiledFunctionJSONObject:
        function_json = super().to_json()
        return {'assembly': self.assembly, 'architecture': self.architecture,
                **function_json}

    @staticmethod
    def create_uid(file_path: Path, name: str, _repo_path: Optional[Path] = None) -> str:
        return f'{file_path}::{name}'

    @classmethod
    def from_json(cls, json_obj: DecompiledFunctionJSONObject) -> 'DecompiledFunction':
        function = cls(json_obj['uid'], Path(json_obj['path']), json_obj['name'],
                       json_obj['definition'], json_obj['assembly'], json_obj['architecture'])
        function.set_metadata(json_obj['metadata'])
        return function

    @no_type_check
    @classmethod
    def from_decompiled_json(cls, json_obj: JSONObject) -> 'DecompiledFunction':
        return cls(DecompiledFunction.create_uid(Path(json_obj['path']), json_obj['name']),
                   Path(json_obj['path']
                        ), json_obj['name'], json_obj['definition'],
                   json_obj['assembly'], json_obj['architecture'])
