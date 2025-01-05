import logging

from rich.logging import RichHandler

from codablellm.core import extractor, decompiler
from codablellm.repoman import create_source_dataset, create_decompiled_dataset, compile_dataset

__version__ = '1.0.0'
__all__ = ['create_source_dataset',
           'create_decompiled_dataset', 'compile_dataset',
           'extractor', 'decompiler']

# Configure logger
logging.basicConfig(
    level=logging.NOTSET, format='%(message)s', datefmt='[%X]', handlers=[RichHandler()]
)
logger = logging.getLogger('rich')
