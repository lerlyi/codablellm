from abc import ABC, abstractmethod
import time
import logging

from collections.abc import Iterator
from concurrent.futures import Future, ProcessPoolExecutor, ThreadPoolExecutor, wait
from contextlib import contextmanager
from multiprocessing.context import BaseContext
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.progress import Progress as BaseProgress
from rich.progress import BarColumn, GetTimeCallable, MofNCompleteColumn, ProgressColumn, \
    TextColumn, TimeElapsedColumn, TimeRemainingColumn
from threading import Lock
from types import TracebackType
from typing import Any, Callable, Concatenate, Deque, Generator, Generic, Iterable, List, \
    Mapping, Optional, Tuple, Type, TypeVar, Union

from codablellm.core import utils

logger = logging.getLogger('codablellm')


class Progress(BaseProgress):

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
        return self.tasks[self._task].completed

    @property
    def total(self) -> Optional[float]:
        return self.tasks[self._task].total

    @property
    def errors(self) -> int:
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


I = TypeVar('I')
R = TypeVar('R')
T = TypeVar('T')

SubmitCallable = Callable[Concatenate[I, ...], R]


class CallablePoolProgress(ABC, Generic[I, R, T]):

    def __init__(self, pool: 'ProcessPoolProgress[I, R]') -> None:
        super().__init__()
        self._pool = pool

    @property
    def pool(self) -> 'ProcessPoolProgress[I, R]':
        return self._pool

    @abstractmethod
    def get_results(self) -> T:
        pass

    def __call__(self) -> T:
        with self.pool:
            return self.get_results()


class ProcessPoolProgress(Iterator[R], Generic[I, R]):

    def __init__(self, submit: SubmitCallable[I, R], iterables: Iterable[I], progress: Progress,
                 max_workers: Optional[int] = None,
                 mp_context: Optional[BaseContext] = None,
                 initializer: Optional[Callable[[], object]] = None,
                 initargs: Tuple[Any, ...] = (), *,
                 max_tasks_per_child: Optional[int] = None,
                 submit_args: Tuple[Any, ...] = (), submit_kwargs: Mapping[str, Any] = {}):
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

    def __enter__(self) -> 'ProcessPoolProgress[I, R]':

        def callback(future: Future[R]) -> None:
            nonlocal self
            if not future.cancelled():
                exception = future.exception()
                if exception:
                    logger.warning('Error occured during batch operation: '
                                   f'{exception}')
                    self._progress.advance(errors=True)
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
                time.sleep(0.1)
            return self._new_results.pop()
        raise StopIteration()

    @property
    def errors(self) -> int:
        return self._progress.errors

    @staticmethod
    @contextmanager
    def multi_progress(*pools_and_results: Tuple['CallablePoolProgress[Any, Any, Any]', Deque[Any]],
                       title: Optional[str] = None) -> Generator[Live, None, None]:

        def get_results(pool: 'CallablePoolProgress[Any, Any, Any]',
                        results: Deque[Any]) -> None:
            result = pool()
            try:
                results.extend(result)
            except TypeError:
                results.append(result)

        table = Table(title=title)
        futures: List[Future[None]] = []
        lock = Lock()
        with ThreadPoolExecutor() as executor:
            for pool, results in pools_and_results:
                with lock:
                    pool.pool._multi_progress = True
                    table.add_row(pool.pool._progress)
                futures.append(executor.submit(get_results, pool, results))
            with Live(table) as live:
                yield live
            wait(futures)
