"""Representation of packages."""

from __future__ import annotations
from functools import cache
from pathlib import Path
from re import Match, fullmatch
from subprocess import check_call
from typing import NamedTuple, Optional

from repotool.version import Version


__all__ = [
    'REGEX',
    'SUFFIX',
    'REGEX',
    'PackageFile',
    'PackageInfo',
    'is_package',
    'sign',
    'signature'
]


SUFFIX = r'(x86_64|i686|any)\.pkg\.tar(\.(xz,gz,zst,bz2,lzop))?$'
REGEX = r'^.+-' + SUFFIX


class PackageInfo(NamedTuple):
    """Package information."""

    pkgbase: str
    version: Version
    arch: str
    compression: Optional[str]


class PackageFile(type(Path())):
    """Package meta information."""

    def __iter__(self):
        yield from self.package_info

    @property
    def info(self):
        """Returns the pacakge base and version."""
        return f'{self.pkgbase} {self.version}'

    @property
    def package_info(self) -> PackageInfo:
        """Returns the respective package info."""
        return get_package_info(self)

    @property
    def pkgbase(self) -> str:
        """Returns the pkgbase."""
        return self.package_info.pkgbase

    @property
    def version(self) -> Version:
        """Returns the version."""
        return self.package_info.version

    @property
    def arch(self) -> str:
        """Returns the architecture."""
        return self.package_info.arch

    @property
    def compression(self) -> str:
        """Returns the compression."""
        return self.package_info.compression

    def is_other_version_of(self, other: Version) -> bool:
        """Checks if the other package is considered
        another version of this pacakge.
        """
        if self.pkgbase != other.pkgbase:
            return False

        if self.version != other.version:
            return True

        if self.compression != other.compression:
            return True

        return False


@cache
def get_package_info(path: Path) -> PackageInfo:
    """Returns the package information from the given file path."""

    pkgbase, version, build, arch_suffix = path.name.rsplit('-', maxsplit=3)
    version = Version(version, int(build))
    arch, compression = fullmatch(SUFFIX, arch_suffix)
    return PackageInfo(pkgbase, version, arch, compression)


@cache
def is_package(package: PackageFile) -> Match:
    """Checks whether the path is a package and returns a regex match."""

    return fullmatch(REGEX, str(package))


def sign(package: PackageFile) -> int:
    """Signs the respective pacakge."""

    return check_call([
        '/usr/bin/gpg', '--output', str(signature(package)), '--detach-sign',
        str(package)
    ])


def signature(package: PackageFile) -> Path:
    """Returns the path to the package's signature."""

    return Path(str(package) + '.sig')
