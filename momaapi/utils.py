import contextlib
from functools import wraps
import os
import time
from typing import Iterable, TypeVar


def assert_type(x, t):
    assert isinstance(x, t)
    return x


def assert_list_type(x, t):
    return [assert_type(xx, t) for xx in assert_type(x, list)]


T = TypeVar("T")

def only(it: Iterable[T]) -> T:
    x, = it
    return x


def timeit(f):
    @wraps(f)
    def _timeit(*args, **kwargs):
        ts = time.time()
        result = f(*args, **kwargs)
        te = time.time()
        print(f"{f.__module__}.{f.__name__}() took {te-ts} sec")
        return result

    return _timeit


def supress_stdout(func):
    def wrapper(*a, **ka):
        with open(os.devnull, "w") as devnull:
            with contextlib.redirect_stdout(devnull):
                return func(*a, **ka)

    return wrapper
