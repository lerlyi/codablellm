'''
Functionality for creating dashboards of complex processes.
'''

from abc import ABC, abstractmethod
from collections.abc import Iterator
from concurrent.futures import Future, ProcessPoolExecutor, ThreadPoolExecutor
import logging
from multiprocessing.context import BaseContext
import os
from queue import Queue
import signal
import time
from types import FrameType, TracebackType
from typing import (Any, Callable, Concatenate, Final, Generic, Iterable, List,
                    Mapping, Optional, Tuple, Type, TypeVar, Union)

from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.progress import Progress as BaseProgress
from rich.progress import (BarColumn, GetTimeCallable, MofNCompleteColumn, ProgressColumn,
                           TextColumn, TimeElapsedColumn, TimeRemainingColumn)

from codablellm.core import utils
from codablellm.exceptions import CodableLLMError

logger = logging.getLogger('codablellm')


class Progress(BaseProgress):
    '''
    A progress bar that can be used to track the progress of a task.
    '''

    def __init__(self, task: str,
                 columns: Iterable[Union[str, ProgressColumn]] = [TextColumn('{task.description}'),
                                                                  BarColumn(),
                                                                  MofNCompleteColumn(),
                                                                  TextColumn(
                                                                      '[b gray]Time Elapsed:'),
                                                                  TimeElapsedColumn(),
                                                                  TextColumn(
                                                                      '[b green]Estimated Time Remaining:'),
                                                                  TimeRemainingColumn(),
                                                                  TextColumn('[b yellow]Errors: {task.fields[errors]}')],
                 total: Optional[float] = None, console: Optional[Console] = None,
                 auto_refresh: bool = True, refresh_per_second: float = 10,
                 speed_estimate_period: float = 30,
                 transient: bool = False, redirect_stdout: bool = True,
                 redirect_stderr: bool = True, get_time: Optional[GetTimeCallable] = None,
                 disable: bool = False, expand: bool = False) -> None:
        super().__init__(*columns, console=console, auto_refresh=auto_refresh,
                         refresh_per_second=refresh_per_second,
                         speed_estimate_period=speed_estimate_period, transient=transient,
                         redirect_stdout=redirect_stdout, redirect_stderr=redirect_stderr,
                         get_time=get_time, disable=disable, expand=expand)
        self._task = super().add_task(task, total=total, errors=0)

    @property
    def completed(self) -> float:
        '''
        The number of completed tasks.

        Returns:
            The number of completed tasks.
        '''
        return self.tasks[self._task].completed

    @property
    def total(self) -> Optional[float]:
        '''
        The total number tasks.

        Returns:
            The total number tasks.
        '''
        return self.tasks[self._task].total

    @property
    def errors(self) -> int:
        '''
        The number of errors that have occurred during the progress.

        Returns:
            The total number of errors.
        '''
        return self.tasks[self._task].fields['errors']

    def advance(self, errors: bool = False, advance: float = 1) -> None:
        if not errors:
            super().advance(self._task, advance)
        else:
            self.update(errors=self.errors + int(advance))

    def update(self, *, total: Optional[float] = None, completed: Optional[float] = None,
               advance: Optional[float] = None, description: Optional[str] = None,
               visible: Optional[bool] = None, refresh: bool = False, errors: Optional[int] = None) -> None:
        super().update(self._task, total=total, completed=completed, advance=advance,
                       description=description, visible=visible, refresh=refresh,
                       **utils.resolve_kwargs(errors=errors))


I_co = TypeVar('I_co', covariant=True)
R = TypeVar('R')
T = TypeVar('T')

SubmitCallable = Callable[Concatenate[I_co, ...], R]
'''
A callable object that is provided to `ProcessPoolExecutor.submit`.
'''


class CallablePoolProgress(ABC, Generic[I_co, R, T]):
    '''
    Abstract base class representing a callable wrapper around a process pool with progress tracking.

    This class allows deferred execution of a process pool with built-in progress handling and 
    provides a mechanism to retrieve results after completion.
    '''

    def __init__(self, pool: 'ProcessPoolProgress[I_co, R]') -> None:
        '''
        Initializes the callable pool progress wrapper.

        Parameters:
            pool: The `ProcessPoolProgress` instance to manage and execute.
        '''
        super().__init__()
        self._pool = pool

    @property
    def pool(self) -> 'ProcessPoolProgress[I_co, R]':
        '''
        The associated `ProcessPoolProgress` instance.

        Returns:
            The `ProcessPoolProgress` instance.
        '''
        return self._pool

    @abstractmethod
    def get_results(self) -> T:
        '''
        Abstract method to retrieve results after the pool execution completes.

        Returns:
            The final processed result.
        '''
        pass

    def __call__(self) -> T:
        '''
        Executes the process pool and returns the results.

        Returns:
            The final processed result.
        '''
        with self.pool:
            return self.get_results()


class ProcessPoolProgress(Iterator[R], Generic[I_co, R]):
    '''
    A process pool executor with integrated progress tracking and graceful shutdown handling.

    This class manages task submission, monitors results, handles exceptions, and 
    displays progress updates during parallel execution.
    '''

    MAIN_PID: Final[int] = os.getpid()
    '''
    The PID of the main process, used for graceful shutdown handling.
    '''
    _ACTIVE_POOLS: Final[List['ProcessPoolProgress[Any, Any]']] = []
    _gracefully_shutting_down: bool = False

    def __new__(cls, *args: Any, **kwargs: Any) -> 'ProcessPoolProgress':
        # Setup graceful shutdown for all process pools when SIGINT is received
        signal.signal(signal.SIGINT,
                      ProcessPoolProgress._gracefully_shutdown_pools)
        return super().__new__(cls)

    def __init__(self, submit: SubmitCallable[I_co, R], iterables: Iterable[I_co], progress: Progress,
                 max_workers: Optional[int] = None,
                 mp_context: Optional[BaseContext] = None,
                 initializer: Optional[Callable[[], object]] = None,
                 initargs: Tuple[Any, ...] = (), *,
                 max_tasks_per_child: Optional[int] = None,
                 submit_args: Tuple[Any, ...] = (), submit_kwargs: Mapping[str, Any] = {}):
        '''
        Initializes the process pool progress manager.

        Parameters:
            submit: A callable used to process each item in `iterables`.
            iterables: The iterable of input items to process in parallel.
            progress: A `Progress` instance for tracking task completion.
            max_workers: Maximum number of worker processes.
            mp_context: Multiprocessing context.
            initializer: Optional initializer function for each worker process.
            initargs: Arguments passed to the initializer.
            max_tasks_per_child: Maximum tasks per worker process before restarting.
            submit_args: Additional positional arguments passed to each `submit` call.
            submit_kwargs: Additional keyword arguments passed to each `submit` call.
        '''
        self._submit = submit
        self._iterables = iterables
        self._progress = progress
        self._process_pool_executor = ProcessPoolExecutor(max_workers=max_workers,
                                                          mp_context=mp_context,
                                                          initializer=initializer,
                                                          initargs=initargs,
                                                          max_tasks_per_child=max_tasks_per_child)
        self._futures: List[Future[R]] = []
        self._new_results: List[R] = []
        self._submit_args = submit_args
        self._submit_kwargs = submit_kwargs
        self._multi_progress = False
        ProcessPoolProgress._ACTIVE_POOLS.append(self)

    def __del__(self) -> None:
        ProcessPoolProgress._ACTIVE_POOLS.remove(self)

    def __enter__(self) -> 'ProcessPoolProgress[I_co, R]':

        def callback(future: Future[R]) -> None:
            nonlocal self
            if not future.cancelled():
                exception = future.exception()
                if exception:
                    self._progress.advance(errors=True)
                    if not isinstance(exception, CodableLLMError):
                        logger.error('Unexpected error occured during batch operation: '
                                     f'{type(exception).__name__}: {exception}')
                    else:
                        logger.warning('Error occured during batch operation: '
                                       f'{type(exception).__name__}: {exception}')
                else:
                    self._new_results.append(future.result())
                    self._progress.advance()

        if not self._multi_progress:
            self._progress.__enter__()
        self._process_pool_executor.__enter__()
        self._futures = [self._process_pool_executor.submit(self._submit, i, *self._submit_args,
                                                            **self._submit_kwargs)
                         for i in self._iterables]
        for future in self._futures:
            future.add_done_callback(callback)
        return self

    def __exit__(self, exc_type: Optional[Type[BaseException]], exc_value: Optional[BaseException],
                 traceback: Optional[TracebackType]) -> None:
        if not self._multi_progress:
            self._progress.__exit__(exc_type, exc_value, traceback)
        self._process_pool_executor.__exit__(exc_type, exc_value, traceback)
        self._futures.clear()

    def __next__(self) -> R:
        if not all(f.done() for f in self._futures) or any(self._new_results):
            while not any(self._new_results):
                if all(f.done() for f in self._futures):
                    raise StopIteration()
                time.sleep(0.1)
            return self._new_results.pop()
        raise StopIteration()

    @property
    def errors(self) -> int:
        '''
        The number of errors encountered during processing.

        Returns:
            The total number of errors.
        '''
        return self._progress.errors

    @staticmethod
    def _gracefully_shutdown_pools(signum: int, frame: Optional[FrameType]) -> None:
        if not ProcessPoolProgress._gracefully_shutting_down:
            if os.getpid() == ProcessPoolProgress.MAIN_PID:
                logger.warning('Gracefully shutting down all process pools...')
                ProcessPoolProgress._gracefully_shutting_down = True
                for pool in ProcessPoolProgress._ACTIVE_POOLS:
                    pool._process_pool_executor.shutdown(wait=False,
                                                         cancel_futures=True)
        else:
            signal.default_int_handler(signum, frame)

    @staticmethod
    def multi_progress(*pools: 'CallablePoolProgress[Any, Any, Any]',
                       title: Optional[str] = None) -> Tuple[List[Any], ...]:
        '''
        Runs multiple `CallablePoolProgress` instances concurrently with a shared progress display.

        Parameters:
            *pools: Multiple callable pool progress objects to run in parallel.
            title: Optional title for the combined progress table display.

        Returns:
            A tuple of lists, where each list contains the results from one of the provided pools.
        '''

        def get_results(pool: 'CallablePoolProgress[Any, Any, Any]',
                        results: Queue[Any]) -> None:
            result = pool()
            try:
                for r in result:
                    results.put(r)
            except TypeError:
                results.put(result)
        pools_and_results = [(p, Queue()) for p in pools]
        table = Table(title=title)
        futures: List[Future[None]] = []
        with ThreadPoolExecutor() as executor:
            for pool, results in pools_and_results:
                pool.pool._multi_progress = True
                table.add_row(pool.pool._progress)
                futures.append(executor.submit(get_results, pool, results))
            with Live(table):
                while not all(f.done() for f in futures):
                    time.sleep(0.1)
        return tuple(list(utils.iter_queue(r[1])) for r in pools_and_results)
