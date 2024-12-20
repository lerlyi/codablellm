from collections import deque
from typing import List
from codablellm.core import *
from codablellm.core.dashboard import ProcessPoolProgress


def test_progress() -> None:
    with Progress('Doing some task...') as progress:
        progress.advance()
        assert progress.completed == 1
        progress.advance(errors=True, advance=2)
        assert progress.errors == 2
        progress.update(completed=0)
        assert progress.completed == 0
        progress.update(errors=0)
        assert progress.errors == 0


def add_numbers(left: int, right: int) -> int:
    return left + right


def test_process_pool_progress() -> None:
    numbers = [1, 2, 3, 4, 5, None]
    with ProcessPoolProgress(add_numbers, numbers,
                             Progress('Adding 3 to numbers...',
                                      total=len(numbers)),
                             submit_args=(3,)) as pool:
        sums = list(pool)
    for number in numbers[:-1]:
        assert number + 3 in sums
    assert pool.errors == 1


def concat_strs(left: str, right: str) -> str:
    return left + right


class CallableAdd(CallablePoolProgress[int, int, List[int]]):

    def __init__(self, numbers: List[int], add_first: int, add_second) -> None:
        super().__init__(ProcessPoolProgress(add_numbers, numbers,
                                             Progress(f'Adding {add_first} to numbers...',
                                                      total=len(numbers)),
                                             submit_args=(add_first,)))
        self.add_second = add_second

    def get_results(self) -> List[int]:
        return [n + self.add_second for n in self.pool]


class CallableConcat(CallablePoolProgress[str, str, List[str]]):

    def __init__(self, strings: List[str], concat_first: str, concat_second: str) -> None:
        super().__init__(ProcessPoolProgress(concat_strs, strings,
                                             Progress(f'Concatenating "{concat_first}" to strings...',
                                                      total=len(strings)),
                                             submit_args=(concat_first,)))
        self.concat_second = concat_second

    def get_results(self) -> List[str]:
        return [s + self.concat_second for s in self.pool]


def test_multi_progress() -> None:
    numbers = [1, 2, 3, 4, 5, None]
    strings = ['foo', 'bar', 'baz']
    add, concat = CallableAdd(
        numbers, 3, 5), CallableConcat(strings, 'bar', 'baz')
    sums, concat_results = deque(), deque()
    with ProcessPoolProgress.multi_progress((add, sums), (concat, concat_results)):
        pass
    for number in numbers[:-1]:
        assert number + 3 + 5 in sums
    for string in strings:
        assert f'{string}barbaz' in concat_results
