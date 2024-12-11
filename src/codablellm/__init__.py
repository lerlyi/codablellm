import logging

from rich.logging import RichHandler

__version__ = '1.0.0'

# Configure logger
logging.basicConfig(
    level=logging.NOTSET, format='%(message)s', datefmt='[%X]', handlers=[RichHandler()]
)
logger = logging.getLogger('rich')
