"""Package version representation and operations."""

from functools import lru_cache
from subprocess import check_output


__all__ = ['Version', 'vercmp']


@lru_cache()
def vercmp(version: str, other: str) -> int:
    """Compares package versions."""

    return int(check_output(('/usr/bin/vercmp', version, other), text=True))


class Version(str):
    """A package version."""

    def __hash__(self):
        return hash((type(self), str(self)))

    def __eq__(self, other):
        return vercmp(str(self), str(other)) == 0

    def __gt__(self, other):
        return vercmp(str(self), str(other)) == 1

    def __lt__(self, other):
        return vercmp(str(self), str(other)) == -1
