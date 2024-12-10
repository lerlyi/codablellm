import logging

from rich.logging import RichHandler

# Configure logger
logging.basicConfig(
    level=logging.NOTSET, format='%(message)s', datefmt='[%X]', handlers=[RichHandler()]
)
logger = logging.getLogger('rich')
