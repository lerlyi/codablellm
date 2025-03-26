'''
Classes pertaining to functions used in code datasets.
'''
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
    '''
    Base class for functions used in datasets.
    '''
    uid: str
    '''
    A unique identifier for the function. This should be unique across all functions in a dataset.
    '''
    path: Path
    '''
    Absolute path to the file containing the function.
    '''
    name: str
    '''
    The name of the function.
    '''
    definition: str
    '''
    The source code of the function.
    '''
    _metadata: Dict[str, Any] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if not self.path.is_absolute():
            raise ValueError('Path to source code file must be absolute.')

    @property
    def metadata(self) -> Mapping[str, Any]:
        '''
        A read-only view of the metadata associated with the function.

        Returns:
            A mapping containing the metadata associated with the function.
        '''
        return {k: v for k, v in self._metadata.items()}

    def set_metadata(self, metadata: Mapping[str, Any]) -> None:
        '''
        Sets the metadata associated with the function. This will overwrite any existing metadata.

        Parameters:
            metadata: A mapping containing the metadata to associate with the function.

        Raises:
            KeyError: If the metadata contains a key that is the same as an existing class field.
        '''
        class_fields = {f.name for f in fields(self)}
        for key, value in metadata.items():
            if key in class_fields:
                raise KeyError(f'Cannot set metadata "{key}" '
                               'to an existing class field')
            self._metadata[key] = value

    def add_metadata(self, metadata: Mapping[str, Any]) -> None:
        '''
        Adds metadata to the function. This will overwrite any existing metadata with the same key.

        Parameters:
            metadata: A mapping containing the metadata to add to the function.
        '''
        return self.set_metadata({**metadata, **self._metadata})

    def remove_metadata(self, key: str) -> None:
        '''
        Removes a metadata entry from the function.

        Parameters:
            key: The key of the metadata entry to remove.
        '''
        del self._metadata[key]

    def to_json(self) -> FunctionJSONObject:
        return {'uid': self.uid, 'path': str(self.path), 'definition': self.definition,
                'name': self.name, 'metadata': self._metadata}

    @staticmethod
    def create_uid(file_path: Path, name: str, repo_path: Optional[Path] = None) -> str:
        '''
        Creates a unique identifier for a function.

        The UID is constructed based on the function's file path and name. If a repository path is
        provided, the UID uses the file's relative path from the repository root to ensure
        precision across different subdirectories.

        Parameters:
            file_path: The path to the source code file containing the function definition.
            name: The name of the function.
            repo_path: Optional repository root path to calculate the relative file path. If provided, the UID is constructed using the relative path from the repository root.

        Returns:
            A string UID in the format of `<relative_path_or_filename>::<function_name>`.

        Raises:
            ValueError: If the given `file_path` is not a subpath of `repo_path`.
        '''
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
        '''
        Extracts the function name from a UID.

        Parameters:
            uid: The unique identifier of the function.

        Returns:
            The function name.
        '''
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
    '''
    A subroutine extracted from source code.
    '''
    language: str
    '''
    The programming language of the source code.
    '''
    start_byte: int
    '''
    The starting byte offset of the function definition in the source code file.
    '''
    end_byte: int
    '''
    The ending byte offset of the function definition in the source code file.
    '''
    class_name: Optional[str] = None
    '''
    The name of the class containing the function, if applicable.
    '''

    def __post_init__(self) -> None:
        if self.start_byte < 0:
            raise ValueError('Start byte must be a non-negative integer')
        if self.start_byte > self.end_byte:
            raise ValueError('Start byte must be less than end byte')

    @property
    def is_method(self) -> bool:
        '''
        Indicates whether the function is a method of a class.

        Returns:
            `True` if the function is defined within a class.
        '''
        return self.class_name is not None

    def with_definition(self, definition: str, name: Optional[str] = None,
                        write_back: bool = True, metadata: Mapping[str, Any] = {}) -> 'SourceFunction':
        '''
        Creates a new `SourceFunction` instance with an updated definition and optional new name.

        This method generates a new UID if a new name is provided, merges existing and new metadata,  
        and optionally writes the updated definition back to the source file.

        Parameters:
            definition: The new function definition to use.
            name: Optional new function name. If not provided, retains the current function name and UID.
            write_back: If `True`, writes the updated definition to the original source file.
            metadata: Additional metadata to merge with the existing function metadata.

        Returns:
            A new `SourceFunction` instance with the updated definition and metadata.
        '''
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
        '''
        Creates a unique identifier (UID) for a source function to be used as a dataset key.

        The UID is based on the function's file path and name, and optionally includes the class name 
        if the function is a method. If a repository path is provided, the UID uses the relative file path.

        Parameters:
            file_path: The full file path of the function definition.
            name: The name of the function.
            repo_path: Optional repository root path for relative path calculation.
            class_name: The class name to include in the UID if the function is a method.

        Returns:
            A UID string in the format: `<relative_path_or_filename>::<class_name>.<function_name>` if `class_name` is provided, otherwise `<relative_path_or_filename>::<function_name>`.
        '''
        uid = Function.create_uid(file_path, name, repo_path=repo_path)
        if class_name:
            scope, function = uid.rsplit('::', maxsplit=1)
            uid = f'{scope}::{class_name}.{function}'
        return uid

    @staticmethod
    def get_function_name(uid: str) -> str:
        '''
        Extracts the function name from a UID, removing any class name prefix.

        Parameters:
            uid: The unique identifier of the function.

        Returns:
            The function name.
        '''
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
        '''
        Creates a `SourceFunction` instance from source code information.

        Parameters:
            file_path: The file path where the function is defined.
            language: The programming language of the function.
            definition: The full source code of the function definition.
            name: The function name.
            start_byte: The starting byte offset of the function in the source file.
            end_byte: The ending byte offset of the function in the source file.
            class_name: Optional name of the class containing the function.
            repo_path: Optional repository root path for relative UID creation.
            metadata: Additional metadata to associate with the function.

        Returns:
            A `SourceFunction` instance populated with the given information and metadata.
        '''
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
'''
Tree-sitter query used to extract all C symbols from a function definition.
'''

C_PARSER: Final[Parser] = Parser(Language(tsc.language()))
'''
Tree-sitter parser for C code.
'''


@dataclass(frozen=True)
class DecompiledFunction(Function):
    '''
    A decompiled function extracted from a compiled binary file.
    '''
    assembly: str
    '''
    Assembly code of the function.
    '''
    architecture: str
    '''
    The architecture of the binary file from which the function was decompiled.
    '''

    def to_stripped(self) -> 'DecompiledFunction':
        '''
        Creates a stripped version of the decompiled function with anonymized symbol names.

        This method replaces all function symbols in both the function definition and assembly code
        with generated placeholders (e.g., `sub_<uuid>`), ensuring sensitive or original identifiers
        are removed. The resulting `DecompiledFunction` has an updated definition, stripped function name, 
        and modified assembly code.

        Returns:
            A new `DecompiledFunction` instance with stripped symbols and updated assembly.
        '''
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
        '''
        Creates a UID for a function based on its file path and name.

        Parameters:
            file_path: The full file path of the function definition.
            name: The name of the function.

        Returns:
            A UID string in the format: `<file_path>::<function_name>`.
        '''
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
