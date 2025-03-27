'''
codablellm is a framework for creating and curating high-quality code datasets tailored for large language models
'''

import logging

from rich.logging import RichHandler

from codablellm.core import extractor, decompiler, ExtractConfig, DecompileConfig
from codablellm.dataset import SourceCodeDatasetConfig, DecompiledCodeDatasetConfig
from codablellm.repoman import (create_source_dataset, create_decompiled_dataset,
                                compile_dataset, ManageConfig)

__version__ = '1.0.5dev2'
__all__ = ['create_source_dataset',
           'create_decompiled_dataset', 'compile_dataset',
           'extractor', 'decompiler', 'ExtractConfig', 'DecompileConfig',
           'ManageConfig', 'SourceCodeDatasetConfig', 'DecompiledCodeDatasetConfig']

# Configure logger
logging.basicConfig(
    level=logging.INFO, format='%(message)s', datefmt='[%X]', handlers=[RichHandler()]
)
logger = logging.getLogger('rich')
