import logging

from rich.logging import RichHandler

from codablellm.core import extractor, decompiler, ExtractConfig, DecompileConfig, rate_limiter
from codablellm.dataset import SourceCodeDatasetConfig, DecompiledCodeDatasetConfig
from codablellm.repoman import (create_source_dataset, create_decompiled_dataset,
                                compile_dataset, ManageConfig)

__version__ = '1.0.0'
__all__ = ['create_source_dataset',
           'create_decompiled_dataset', 'compile_dataset',
           'extractor', 'decompiler', 'ExtractConfig', 'DecompileConfig',
           'ManageConfig', 'SourceCodeDatasetConfig', 'DecompiledCodeDatasetConfig',
           'rate_limiter']

# Configure logger
logging.basicConfig(
    level=logging.INFO, format='%(message)s', datefmt='[%X]', handlers=[RichHandler()]
)
logger = logging.getLogger('rich')
