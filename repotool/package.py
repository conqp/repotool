"""Representation of packages."""

from __future__ import annotations
from functools import lru_cache
from pathlib import Path
from re import Match, fullmatch
from subprocess import check_call

from repotool.version import Version


__all__ = ['GLOB', 'REGEX', 'Package', 'is_package', 'sign', 'signature']


GLOB = '*.pkg.tar*'
REGEX = '^.*-(x86_64|i686|any)\\.pkg\\.tar(\\.[a-z]{2,3})?$'


@lru_cache()
def get_arch_and_compression(path: Path) -> tuple[str, str]:
    """Returns the architecture and file compression."""

    return is_package(path).groups()


@lru_cache()
def get_pkgbase_and_version(path: Path) -> tuple[str, Version]:
    """Returns the pkgbase and version from the given file path."""

    pkgbase, version, build = path.name.rsplit('-', maxsplit=2)
    return (pkgbase, Version(version, int(build)))


@lru_cache()
def is_package(string: str) -> Match:
    """Checks whether the path is a package and returns a regex match."""

    if not isinstance(string, str):
        return is_package(str(string))

    return fullmatch(REGEX, string)


def sign(package: Package) -> int:
    """Signs the respective pacakge."""

    return check_call([
        '/usr/bin/gpg', '--output', str(signature(package)), '--detach-sign',
        str(package)
    ])


def signature(package: Package) -> Path:
    """Returns the path to the package's signature."""

    return Path(str(package) + '.sig')


class Package(type(Path())):
    """Package meta information."""

    def __iter__(self):
        """Yields the package's properties."""
        yield self.pkgbase
        yield self.version
        yield self.arch
        yield self.compression

    @property
    def info(self):
        """Returns the pacakge base and version."""
        return f'{self.pkgbase} {self.version}'

    @property
    def pkgbase(self):
        """Returns the pkgbase."""
        return get_pkgbase_and_version(self)[0]

    @property
    def version(self):
        """Returns the package version."""
        return get_pkgbase_and_version(self)[1]

    @property
    def arch(self):
        """Returns the package architecture."""
        return get_arch_and_compression(self)[0]

    @property
    def compression(self):
        """Returns the package compression."""
        return get_arch_and_compression(self)[1]

    def is_other_version_of(self, other: Version) -> bool:
        """Checks if the other package is considered
        another version of this pacakge.
        """
        if self.pkgbase == other.pkgbase:
            if self.version != other.version:
                return True

            if self.compression != other.compression:
                return True

        return False
