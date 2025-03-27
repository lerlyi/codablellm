'''
Code dataset generation.
'''

from abc import ABC, abstractmethod
from collections.abc import Mapping
from contextlib import nullcontext
from dataclasses import dataclass, field
from functools import wraps
import logging
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from typing import (Any, Callable, Dict, Final, Iterable, Iterator, List, Literal,
                    Sequence, Tuple, TypeVar, Union, overload)

from pandas import DataFrame

from codablellm.core import decompiler, extractor, utils
from codablellm.core.dashboard import ProcessPoolProgress, Progress
from codablellm.core.function import DecompiledFunction, SourceFunction
from codablellm.exceptions import TSParsingError

logger = logging.getLogger('codablellm')


class Dataset(ABC):
    '''
    A code dataset.
    '''

    @abstractmethod
    def to_df(self) -> DataFrame:
        '''
        Converts the code dataset to a pandas DataFrame.

        Returns:
            A pandas DataFrame representation of the code dataset.
        '''
        pass

    def save_as(self, path: utils.PathLike) -> None:
        '''
        Converts the dataset to a DataFrame and exports it to the specified file path based on
        its extension. The export format is determined by the file extension provided in the
        `path` parameter.

        Example:
            ```py
            dataset.save_as("output.xlsx")
            ```

            Successfully saves the dataset as an Excel file to "output.xlsx".

        Supported Formats and Extensions:
            - JSON: .json, .jsonl
            - CSV/TSV: .csv, .tsv
            - Excel: .xlsx, .xls, .xlsm **(requires codablellm[excel])**
            - Markdown: .md, .markdown **(requires codablellm[markdown])**
            - LaTeX: .tex
            - HTML: .html, .htm
            - XML: .xml **(requires codablellm[xml])**

        Parameters:
            path: Path to save the dataset at.

        Raises:
            ValueError: If the provided file extension is unsupported.
            ExtraNotInstalled: If the file extension requires an additional library that is not installed.
        '''

        @utils.requires_extra('excel', 'Excel exports', 'openpyxl')
        def to_excel(df: DataFrame, path: Path) -> None:
            df.to_excel(path)

        @utils.requires_extra('xml', 'XML exports', 'lxml')
        def to_xml(df: DataFrame, path: Path) -> None:
            df.to_xml(path)

        @utils.requires_extra('markdown', 'Markdown exports', 'tabulate')
        def to_markdown(df: DataFrame, path: Path) -> None:
            df.to_markdown(path)

        path = Path(path)
        extension = path.suffix.casefold()
        if extension in [e.casefold() for e in ['.json', '.jsonl']]:
            self.to_df().to_json(path, lines=extension == '.jsonl'.casefold(), orient='records')
        elif extension in [e.casefold() for e in ['.csv', '.tsv']]:
            self.to_df().to_csv(path, sep=',' if extension == '.csv'.casefold() else '\t')
        elif extension in [e.casefold() for e in ['.xlsx', '.xls', '.xlsm']]:
            to_excel(self.to_df(), path)
        elif extension in [e.casefold() for e in ['.md', '.markdown']]:
            to_markdown(self.to_df(), path)
        elif extension == '.tex'.casefold():
            self.to_df().to_latex(path)
        elif extension in [e.casefold() for e in ['.html', '.htm']]:
            self.to_df().to_html(path)
        elif extension == '.xml'.casefold():
            to_xml(self.to_df(), path)
        else:
            raise ValueError(f'Unsupported file extension: {path.suffix}')
        logger.info(f'Successfully saved {path.name}')


DatasetGenerationMode = Literal['path', 'temp']
'''
How the dataset should be generated.

Generation Modes:
    - **`path`**: Generates the dataset directly from the local repository path.
        - *Note*: If `extract_config.transform` is provided, the source code in the local repository 
        may be overridden by the transformed code.

    - **`temp`**: Copies the repository to a temporary directory and generates the dataset there.
        - *If `extract_config.transform` is not provided, the mode defaults to `path`*.
'''
    # - **`temp-append`**: Copies the repository to a temporary directory, applies the transformation 
    # using `extract_config.transform`, and appends the transformed entries to the original source 
    # code from the local repository.
    #     - *If `extract_config.transform` is not provided, the mode defaults to `path`*.


# TODO: see if there's a way to make this a frozen dataclass


@dataclass
class SourceCodeDatasetConfig:
    '''
    Configuration options for generating a source code dataset.

    This class provides flexible options for controlling how a source code dataset is generated, 
    including handling of temporary directories, extraction settings, and generation modes.
    '''
    generation_mode: DatasetGenerationMode = 'temp'
    '''
    How the source code dataset should be generated.
    '''
    delete_temp: bool = True
    '''
    Controls whether the temporary directory should be deleted after dataset generation.

    - *Applies only if `generation_mode` is set to `temp`. When set to `True`, 
    the temporary directory will be automatically deleted after dataset generation.*
    '''
    extract_config: extractor.ExtractConfig = \
        field(default_factory=extractor.ExtractConfig)
    '''
    Configuration settings for extracting source code functions.
    '''
    log_generation_warning: bool = True

    def __post_init__(self) -> None:
        if (self.generation_mode == 'temp' or self.generation_mode == 'temp-append') and \
                not self.extract_config.transform:
            if self.log_generation_warning:
                logger.warning(f'Generation mode was specified as "{self.generation_mode}", but no '
                               'transform was provided. Changing generation mode to "path" to '
                               'save resources')
            self.generation_mode = 'path'


T = TypeVar('T')


def clear_checkpoints_after() -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    '''
    Decorator that clears all extractor checkpoint files after successful execution of the decorated function.
    '''
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = func(*args, **kwargs)
            for checkpoint_file in extractor.get_checkpoint_files():
                checkpoint_file.unlink(missing_ok=True)
            logger.debug(f'Removed all extractor checkpoints')
            return result
        return wrapper
    return decorator


class SourceCodeDataset(Dataset, Mapping[str, SourceFunction]):
    '''
    A source code dataset.

    This class provides functionality to manage and interact with a collection of 
    source functions, allowing indexing and mapping by unique identifiers (UIDs)
    '''

    def __init__(self, functions: Iterable[SourceFunction]) -> None:
        '''
        Initializes a new source code dataset instance with a collection of source functions.

        Parameters:
            functions: An iterable collection of source code functions used to populate the dataset.
        '''
        super().__init__()
        self._mapping: Dict[str, SourceFunction] = {
            f.uid: f for f in functions
        }

    def __getitem__(self, key: Union[str, SourceFunction]) -> SourceFunction:
        if isinstance(key, SourceFunction):
            return self[key.uid]
        return self._mapping[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._mapping)

    def __len__(self) -> int:
        return len(self._mapping)

    def get(self, key: Union[str, SourceFunction], default: T = None) -> Union[SourceFunction, T]:
        try:
            return self[key]
        except KeyError:
            return default

    def to_df(self) -> DataFrame:
        function_dicts: List[Dict[str, Any]] = []
        for function in self.values():
            function_json = function.to_json()
            function_dict = dict(function_json)
            # Flatten SourceFunction.metadata
            del function_dict['metadata']
            function_dict.update(function_json['metadata'])
            function_dicts.append(function_dict)
        try:
            return DataFrame(function_dicts).set_index('uid')
        except KeyError:
            logger.debug('Could not set DataFrame index to "uid", returning an empty '
                         'DataFrame to assume that the DataFrame is empty')
            return DataFrame()

    def get_common_directory(self) -> Path:
        '''
        Returns the common directory shared by all entries in the dataset. This typically 
        represents the path to the local repository from which the dataset was generated.

        Returns:
            The common directory path for all dataset entries.
        '''
        common_path = Path(os.path.commonpath(p.path for p in self.values()))
        return common_path if common_path.is_dir() else common_path.parent

    @overload
    @classmethod
    def from_repository(cls, path: utils.PathLike,
                        config: SourceCodeDatasetConfig = SourceCodeDatasetConfig(
                            log_generation_warning=False),
                        as_callable_pool: Literal[False] = False) -> 'SourceCodeDataset': ...

    @overload
    @classmethod
    def from_repository(cls, path: utils.PathLike,
                        config: SourceCodeDatasetConfig = SourceCodeDatasetConfig(
                            log_generation_warning=False),
                        as_callable_pool: Literal[True] = True) -> extractor._CallableExtractor: ...

    @classmethod
    @utils.benchmark_function('Source code dataset creation')
    @clear_checkpoints_after()
    def from_repository(cls, path: utils.PathLike,
                        config: SourceCodeDatasetConfig = SourceCodeDatasetConfig(
                            log_generation_warning=False),
                        as_callable_pool: bool = False,) -> Union['SourceCodeDataset',
                                                                  extractor._CallableExtractor]:
        '''
        Creates a source code dataset from a local repository.

        This method scans the specified repository and generates a dataset of source code functions 
        based on the provided configuration. Optionally, it can return a callable pool that allows 
        deferred execution of the dataset generation process.

        Example:
            ```py
            SourceCodeDataset.from_repository('path/to/my/repository',
                                                config=SourceCodeDatasetConfig(
                                                    generation_mode='path'
                                                    extract_config=ExtractConfig(
                                                        transform=remove_comments
                                                    )
                                                )
                                             )
            ```

            Will create a source code dataset from `path/to/my/repository`, overriding the contents
            of the repository and removing all comments from the extracted source code functions.

        Parameters:
            path: Path to the local repository to generate the dataset from.
            config: Configuration settings for dataset generation.
            as_callable_pool: If `True`, returns a `CallablePoolProgress` object that can be executed later to generate the dataset.

        Returns:
            The generated source code dataset if `as_callable_pool` is `False`, or a `CallablePoolProgress` object if `as_callable_pool` is `True`.
        '''
        if config.generation_mode == 'temp-append':
            raise NotImplementedError('temp-append is not yet implemented')
        if config.generation_mode != 'temp-append':
            ctx = TemporaryDirectory(delete=config.delete_temp) if config.generation_mode == 'temp' \
                else nullcontext()
            with ctx as temp_dir:
                if temp_dir:
                    # If a temporary directory was created, copy the repository
                    copied_repo_dir = Path(temp_dir) / Path(path).name
                    shutil.copytree(path, copied_repo_dir)
                    path = copied_repo_dir
                extraction_pool = extractor.extract(path, as_callable_pool=True,
                                                    config=config.extract_config)
                if as_callable_pool:
                    return extraction_pool
                return cls(s for s in extraction_pool())
        # Create a temp configuration for the transformed values
        temp_config = SourceCodeDatasetConfig(
            generation_mode='temp',
            delete_temp=False,
            extract_config=config.extract_config
        )
        transformed_extraction_pool = cls.from_repository(path,
                                                          config=temp_config,
                                                          as_callable_pool=True)
        # Create a path configuration for the non-transformed values
        path_config = SourceCodeDatasetConfig(
            generation_mode='path',
            extract_config=config.extract_config
        )
        original_extraction_pool = cls.from_repository(path,
                                                       config=path_config,
                                                       as_callable_pool=True)
        original_functions, transformed_functions = \
            ProcessPoolProgress.multi_progress(original_extraction_pool,
                                               transformed_extraction_pool,
                                               title='Generating Source Code Dataset')
        # Create temporary transformed and non-transformed datasets
        original_dataset = cls(s for s in original_functions)
        transformed_dataset = cls(s for s in transformed_functions)
        final_functions: List[SourceFunction] = []
        with Progress('Annotating transformed functions...', total=len(transformed_functions)) as progress:
            for transformed_function in transformed_dataset.values():
                source_function = \
                    original_dataset.get(transformed_function)  # type: ignore
                if source_function:
                    # Add transformed_definition and transformed_class_name metadata to the final dataset
                    source_function.add_metadata({'transformed_definition': transformed_function.definition,
                                                  'transformed_class_name': transformed_function.class_name,
                                                  })
                    final_functions.append(source_function)
                    progress.advance()
                else:
                    logger.error(f'Could not locate UID "{transformed_function.uid}" in original '
                                 'source code dataset')
                    progress.advance(errors=True)
            return cls(s for s in final_functions)


def name_mapper(function: DecompiledFunction, uid: Union[SourceFunction, str]) -> bool:
    '''
    Maps a decompiled function to a source function by comparing their function names.

    Parameters:
        function: The decompiled function to map.
        uid: The source function UID or a `SourceFunction` object to map against.

    Returns:
        `True` if the decompiled function name matches the source function name.
    '''
    if isinstance(uid, SourceFunction):
        uid = uid.uid
    return function.name == SourceFunction.get_function_name(uid)


Mapper = Callable[[DecompiledFunction, SourceFunction], bool]
'''
Callable type describing a mapping function that determines if a decompiled function
corresponds to a given source function.
'''

DEFAULT_MAPPER: Final[Mapper] = name_mapper
'''
The default mapping function used to match decompiled functions to source functions.
'''


@dataclass(frozen=True)
class DecompiledCodeDatasetConfig:
    '''
    Configuration options for generating a decompiled dataset.

    This class defines the settings for extracting source code functions from binaries 
    and configuring the decompilation process.
    '''
    extract_config: extractor.ExtractConfig = \
        field(default_factory=extractor.ExtractConfig)
    '''
    Configuration settings for extracting source code functions.
    '''
    decompiler_config: decompiler.DecompileConfig = \
        field(default_factory=decompiler.DecompileConfig)
    '''
    Configuration settings for decompiling binaries.
    '''
    strip: bool = False
    '''
    Indicates whether the decompiled binaries should be stripped

    A Note on Decompiled Code Stripping:
        Stripping occurs after decompilation by replacing the symbols in the decompiled code
        with ambiguous symbols. This approach simulates stripped binaries but does not
        necessarily reflect actual stripped functions because the decompiler may still have
        access to debug symbols during the decompilation process.
    '''
    mapper: Mapper = DEFAULT_MAPPER
    '''
    The mapping function used to determine if a decompiled function corresponds to a given source function.
    '''


class DecompiledCodeDataset(Dataset, Mapping[str, Tuple[DecompiledFunction, SourceCodeDataset]]):
    '''
    A dataset of decompiled functions mapped to their corresponding potential source functions.

    This class provides functionality to manage and interact with decompiled functions 
    and their possible source code counterparts, allowing for easy lookup by unique identifiers (UIDs).
    '''

    def __init__(self,
                 mappings: Iterable[Tuple[DecompiledFunction, SourceCodeDataset]]) -> None:
        '''
        Initializes a new decompiled code dataset instance with a collection of mappings 
        between decompiled functions and their potential source functions.

        Parameters:
            mappings: An iterable collection of 2-tuples, where each tuple consists of the decompiled function and the corresponding potential source functions.
        '''
        super().__init__()
        self._mapping: Dict[str,
                            Tuple[DecompiledFunction, SourceCodeDataset]
                            ] = {
                                m[0].uid: m for m in mappings
        }

    def __getitem__(self, key: Union[str, DecompiledFunction]) -> Tuple[DecompiledFunction, SourceCodeDataset]:
        if isinstance(key, DecompiledFunction):
            return self[key.uid]
        return self._mapping[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._mapping)

    def __len__(self) -> int:
        return len(self._mapping)

    def get(self, key: Union[str, DecompiledFunction], default: T = None) -> Union[Tuple[DecompiledFunction, SourceCodeDataset], T]:
        try:
            return self[key]
        except KeyError:
            return default

    def to_df(self) -> DataFrame:
        function_dicts: List[Dict[str, Any]] = []
        for decompiled_function, source_functions in self.values():
            decompiled_function_json = decompiled_function.to_json()
            decompiled_function_dict = dict(decompiled_function_json)
            # Flatten DecompiledFunction.metadata
            del decompiled_function_dict['metadata']
            decompiled_function_dict.update(
                decompiled_function_json['metadata'])
            # Refactor names to be more specific on decompiled functions and multiple source functions
            decompiled_function_dict['decompiled_uid'] = \
                decompiled_function_dict.pop('uid')
            decompiled_function_dict['bin'] = \
                decompiled_function_dict.pop('path')
            decompiled_function_dict['decompiled_definition'] = \
                decompiled_function_dict.pop('definition')
            source_functions_dict = source_functions.to_df().to_dict()
            source_functions_dict['source_files'] = \
                source_functions_dict.pop('path')
            source_functions_dict['source_definitions'] = \
                source_functions_dict.pop('definition')
            del source_functions_dict['name']
            source_functions_dict['source_file_start_bytes'] = \
                source_functions_dict.pop('start_byte')
            source_functions_dict['source_file_end_bytes'] = \
                source_functions_dict.pop('end_byte')
            source_functions_dict['class_names'] = \
                source_functions_dict.pop('class_name')
            decompiled_function_dict.update(
                source_functions_dict)  # type: ignore
            function_dicts.append(decompiled_function_dict)
        try:
            return DataFrame(function_dicts).set_index('decompiled_uid')
        except KeyError:
            logger.debug('Could not set DataFrame index to "uid", returning an empty '
                         'DataFrame to assume that the DataFrame is empty')
            return DataFrame()

    def lookup(self, key: Union[str, SourceFunction]) -> List[Tuple[DecompiledFunction, SourceCodeDataset]]:
        '''
        Finds all mappings where the given key may correspond to potential source functions.

        The method searches through the dataset and returns all decompiled functions 
        and their associated source code datasets where the specified key matches one of the 
        source functions.

        Parameters:
            key: The key to search for, which can be either a source function UID or a `SourceFunction` object.

        Returns:
            A list of tuples, where each tuple consists of a decompiled function and its 
            corresponding source code dataset containing the potential matches.
        '''
        return [m for m in self.values() if key in m[1]]

    def to_source_code_dataset(self) -> SourceCodeDataset:
        '''
        Converts the decompiled code dataset into a source code dataset.

        This method aggregates all source functions from the decompiled code dataset 
        and constructs a `SourceCodeDataset` containing only the source functions.

        Returns:
            A dataset containing all source functions extracted from the decompiled code dataset.
        '''
        return SourceCodeDataset(f for _, d in self.values() for f in d.values())

    def to_stripped_dataset(self) -> 'DecompiledCodeDataset':
        '''
        Converts the decompiled code dataset into a stripped decompiled code dataset.

        The method applies the stripping process to each decompiled function in the dataset, 
        resulting in a dataset with stripped versions of the decompiled functions.

        Returns:
            A new dataset where all decompiled functions have been stripped.
        '''
        return DecompiledCodeDataset((d.to_stripped(), s) for d, s in self.values())

    @classmethod
    @utils.benchmark_function('Mapping source code to decompiled code')
    def _from_dataset_and_decompiled(cls, source_dataset: SourceCodeDataset,
                                     decompiled_functions: Sequence[DecompiledFunction],
                                     stripped: bool,
                                     mapper: Mapper) -> 'DecompiledCodeDataset':

        function_name_map: Dict[str, List[SourceFunction]] = {}
        for source_function in source_dataset.values():
            function_name_map.setdefault(SourceFunction.get_function_name(source_function.uid),
                                         []).append(source_function)
        mappings: List[Tuple[DecompiledFunction, SourceCodeDataset]] = []
        logger.info('Mapping decompiled functions to source functions...')
        with Progress('Mapping functions...', total=len(decompiled_functions)) as progress:
            for decompiled_function in decompiled_functions:
                source_functions = [s for s in function_name_map.get(decompiled_function.name, [])
                                    if mapper(decompiled_function, s)]
                if source_functions:
                    if stripped:
                        try:
                            decompiled_function = decompiled_function.to_stripped()
                        except (TSParsingError, ValueError):  # TODO: remove ValueError
                            logger.error(
                                f'Could not strip {decompiled_function.uid}')
                            progress.advance(errors=True)
                            progress.advance()
                            continue
                    mappings.append((decompiled_function,
                                    SourceCodeDataset(source_functions)))
                progress.advance()
            logger.info(f'Successfully mapped {len(mappings)} decompiled functions to '
                        f'{sum(len(f) for f in function_name_map.values())} source functions')
            return cls(mappings)

    @classmethod
    @utils.benchmark_function('Decompiled code dataset creation')
    @clear_checkpoints_after()
    def from_repository(cls, path: utils.PathLike, bins: Sequence[utils.PathLike],
                        extract_config: extractor.ExtractConfig = extractor.ExtractConfig(),
                        dataset_config: DecompiledCodeDatasetConfig = DecompiledCodeDatasetConfig()) -> 'DecompiledCodeDataset':
        '''
        Creates a decompiled code dataset from a built local repository.

        This method scans the specified local repository, decompiles the provided binaries, 
        and generates a dataset of decompiled functions mapped to their corresponding potential 
        source code functions based on the provided extraction and dataset configuration.

        Example:
            ```py
            DecompiledCodeDataset.from_repository('path/to/my/repository',
                                                [
                                                'path/to/my/repository/bin1.exe',
                                                'path/to/my/repository/bin2.exe'
                                                ],
                                                extract_config=ExtractConfig(
                                                    transform=remove_comments
                                                ),
                                                dataset_config=DecompiledCodeDatasetConfig(
                                                    strip=True
                                                )
                                             )
            ```

            The above example creates a decompiled code dataset from a copy of 
            `path/to/my/repository`, removes all comments from the extracted source code
            functions, decompiles the binaries `bin1.exe` and `bin2.exe`, and strips the symbols
            after decompilation.

        Parameters:
            path: Path to the local repository to generate the dataset from.
            bins: A sequence of paths to the built binaries of the repository that should be decompiled.
            extract_config: Configuration settings for extracting source code functions. 
            dataset_config: Configuration settings for generating the decompiled code dataset. 

        Returns:
            The generated dataset containing mappings of decompiled functions to their potential source code functions.

        Raises:
            ValueError: If `bins` is an empty sequence.
        '''
        bins = [bins] if isinstance(bins, str) else bins
        if not any(bins):
            raise ValueError('Must at least specify one binary')
        # Extract source code functions and decompile binaries in parallel
        original_extraction_pool = extractor.extract(path, as_callable_pool=True,
                                                     config=extract_config)
        decompile_pool = decompiler.decompile(bins, as_callable_pool=True,
                                              config=dataset_config.decompiler_config)
        source_functions, decompiled_functions = \
            ProcessPoolProgress.multi_progress(original_extraction_pool,
                                               decompile_pool,
                                               title='Generating Decompiled Code Dataset')
        source_dataset = SourceCodeDataset(source_functions)
        return cls._from_dataset_and_decompiled(source_dataset, decompiled_functions,
                                                dataset_config.strip, dataset_config.mapper)

    @classmethod
    @utils.benchmark_function('Decompiled code dataset creation')
    @clear_checkpoints_after()
    def from_source_code_dataset(cls, dataset: SourceCodeDataset, bins: Sequence[utils.PathLike],
                                 config: DecompiledCodeDatasetConfig = DecompiledCodeDatasetConfig()) -> 'DecompiledCodeDataset':
        '''
        Creates a decompiled code dataset from a source code dataset and binaries.

        This method decompiles the provided binaries, and generates a dataset of decompiled
        functions mapped to their corresponding potential source code functions based on the
        provided source code dataset and decompiled code dataset configuration.

        Example:
            ```py
            DecompiledCodeDataset.from_source_code_dataset(dataset,
                                                [
                                                'path/to/my/repository/bin1.exe',
                                                'path/to/my/repository/bin2.exe'
                                                ]
                                                config=DecompiledCodeDatasetConfig(
                                                    strip=True
                                                )
                                             )
            ```

            The above example creates a decompiled code dataset from `dataset`,
            decompiles the binaries `bin1.exe` and `bin2.exe`, and strips the symbols after
            decompilation.

        Parameters:
            dataset: A source code dataset to generate the dataset from.
            bins: A sequence of paths to the built binaries of the repository that should be decompiled.
            config: Configuration settings for generating the decompiled code dataset. 

        Returns:
            The generated dataset containing mappings of decompiled functions to their potential source code functions.
        '''
        return cls._from_dataset_and_decompiled(dataset, decompiler.decompile(bins,
                                                                              config=config.decompiler_config),
                                                config.strip,
                                                config.mapper)
