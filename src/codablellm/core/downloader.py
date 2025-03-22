'''
Module containing functions for downloading remote repositories.
'''

import codablellm.core.utils as utils
import hashlib
import logging
import requests
import tarfile
import zipfile

from git import Repo
from pathlib import Path
from tempfile import NamedTemporaryFile
from rich.progress import BarColumn, DownloadColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn, TransferSpeedColumn
from typing import Optional, Tuple


logger = logging.getLogger('codablellm')


def decompress(url: str, path: Path, checksum: Optional[Tuple[str, str]] = None,
               archive_size: Optional[int] = None,
               chunk_size: int = 2 ** 10 * 8) -> int:
    '''
    Downloads an archive file from the internet and extracts it to a specified directory.

    Parameters:
        url: URL of where the archive is located.
        path: Directory of where the archive should be extracted to.
        checksum: A 2-tuple of containing the type of checksum algorithm to perform, followed by the checksum
        archive_size: Estimated size of the archive.
        chunk_size: The size of each chunk to download in bytes.

    Returns:
        The size of the decompressed archive.

    Raises:
        DownloadError: If there are any issues downloading the archive, decompressing it, or if the checksum comparison failed.
    '''
    if archive_size is None:
        archive_size = 0
    elif archive_size <= 0:
        raise ValueError('archive_size must be a positive integer.')
    if chunk_size <= 0:
        raise ValueError('chunk_size must be a positive integer.')
    with Progress(TextColumn('{task.description}'), SpinnerColumn()) as locate_archive_progress:
        # Perform a GET request and get the archive as bytes
        locate_archive_progress.add_task('Locating archive...', total=None)
        try:
            response = requests.get(url, stream=True)
        except requests.ReadTimeout as e:
            raise ValueError('Cannot retrieve archive.') from e
        if not response.ok:
            raise ValueError('Cannot retrieve archive.')
        logger.info(f'Located archive at {response.url}')
    # Calculate file size
    size = int(response.headers.get('Content-Length', archive_size))
    if size > 0 and 'Content-Length' in response.headers:
        logger.warning(
            f'Will temporarily allocate {utils.get_readable_file_size(size)} of storage ' +
            'for archive.')
    elif size > 0:
        logger.warning(
            f'Will temporarily allocate {utils.get_readable_file_size(size)} of storage (estimate) for ' +
            'archive.')
    else:
        logger.warning(
            'Will temporarily allocate an unspecified amount of storage for archive.')
    try:
        # Download archive
        with Progress(
                TextColumn('{task.description}'), BarColumn(),
                TextColumn('[b]Archive Size:'), DownloadColumn(),
                TextColumn('[b]Speed:'), TransferSpeedColumn(),
                TextColumn('[b]ETA:'), TimeRemainingColumn()) as download_progress:
            download_task = download_progress.add_task(f'Downloading archive...',
                                                       total=size if size > 0 else None)
            with NamedTemporaryFile(delete=False) as file:
                archive_path = Path(file.name)
                logger.debug(f'Downloading archive to {archive_path}')
                for chunk in response.iter_content(chunk_size=chunk_size):
                    file.write(chunk)
                    download_progress.update(download_task,
                                             completed=archive_path.stat().st_size)
            logger.info('Successfully downloaded archive.')
        with Progress(
                TextColumn('{task.description}'), BarColumn(),
                TextColumn('[b]Actual Size:'), DownloadColumn(),
                TextColumn('[b]Speed:'), TransferSpeedColumn(),
                TextColumn('[b]ETA:'), TimeRemainingColumn()) as decompression_progress:
            # If MD5 checksum is specified, check archive integrity
            if checksum:
                try:
                    checksum_func_name, actual_checksum = checksum
                    checksum_func = getattr(
                        hashlib, checksum_func_name.lower())
                    if checksum_func(archive_path.read_bytes()).hexdigest() != actual_checksum:
                        raise ValueError('Archive integrity check failed.')
                except (AttributeError, TypeError) as e:
                    raise ValueError(
                        f'{checksum_func_name} is not a checksum function.')
            # Create extraction directory if it does not already exist
            path.mkdir(parents=True, exist_ok=True)
            # Extract archive
            decompression_task = decompression_progress.add_task('Decompressing archive...',
                                                                 total=None)
            if zipfile.is_zipfile(archive_path):
                with zipfile.ZipFile(archive_path) as zip_file:
                    zipfile_members = zip_file.infolist()
                    decompression_progress.update(decompression_task,
                                                  total=sum(m.file_size for m in zipfile_members))
                    for zipfile_member in zipfile_members:
                        zip_file.extract(zipfile_member, path)
                        decompression_progress.advance(decompression_task,
                                                       advance=zipfile_member.file_size)
            elif tarfile.is_tarfile(archive_path):
                with tarfile.open(archive_path) as tarball:
                    tarball_members = tarball.getmembers()
                    decompression_progress.update(decompression_task,
                                                  total=sum(m.size for m in tarball_members))
                    for tarball_member in tarball_members:
                        tarball.extract(tarball_member, path)
                        decompression_progress.advance(decompression_task,
                                                       advance=tarball_member.size)
            else:
                raise NotImplementedError(
                    'Cannot extract unknown archive type')

            size = int(decompression_progress.tasks[decompression_task].
                       total)  # type: ignore
            logger.info(f'Successfully decompressed {utils.get_readable_file_size(size)} of data to ' +
                        f'{path}')
            return size
    except (zipfile.BadZipFile, tarfile.TarError) as e:
        raise ValueError(f'Could not extract archive to {path}') from e
    finally:
        # Delete archive
        size = archive_path.stat().st_size
        archive_path.unlink()
        logger.debug(f'Removed archive and restored {utils.get_readable_file_size(size)} ' +
                     'of storage.')

def clone(url: str, path: Path) -> int:
    '''
    Downloads an archive file from the internet and extracts it to a specified directory.

    Parameters:
        url: URL of where the archive is located.
        path: Directory of where the archive should be extracted to.
    
    Returns:
        The size of the decompressed archive.
    '''
    return Repo.clone_from(url, path).active_branch.ref.object.size