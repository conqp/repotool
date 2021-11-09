"""Package version representation and operations."""

from functools import lru_cache, total_ordering
from subprocess import check_output
from typing import NamedTuple


__all__ = ['Version', 'vercmp']


@lru_cache()
def vercmp(version: str, other: str) -> int:
    """Compares package versions."""

    return int(check_output(['/usr/bin/vercmp', version, other], text=True))


@total_ordering
class Version(NamedTuple):
    """A package version."""

    version: str
    build: int

    def __str__(self):
        return f'{self.version}-{self.build}'

    def __hash__(self):
        return hash((type(self), str(self)))

    def __eq__(self, other):
        return self.version == other.version and self.build == other.build

    def __lt__(self, other):
        if (cmp := vercmp(self.version, other.version)) == 0:
            return self.build < other.build

        return cmp == -1
