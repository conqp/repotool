"""Manage Arch Linux repositories."""

from contextlib import suppress
from functools import lru_cache
from logging import getLogger
from os import linesep
from pathlib import Path, PosixPath
from re import compile  # pylint: disable=W0622
from shutil import SameFileError, copy2
from subprocess import check_call, check_output
from typing import NamedTuple


__all__ = [
    'NotAPackage',
    'pkgsig',
    'signpkg',
    'pkgpath',
    'vercmp',
    'Version',
    'Package',
    'Repository'
]


LOGGER = getLogger(__file__)
PACKAGELIST = ('/usr/bin/makepkg', '--packagelist')
PKG_GLOB = '*.pkg.tar*'
PKG_REGEX = compile('^.*-(x86_64|i686|any)\\.pkg\\.tar(\\.[a-z]{2,3})?$')


class NotAPackage(Exception):
    """Indicates that the respective path is not a package."""


def pkgsig(package):
    """Returns the path to the package's signature."""

    return Path(str(package) + '.sig')


def signpkg(package):
    """Signs the respective pacakge."""

    return check_call(
        ('/usr/bin/gpg', '--output', str(pkgsig(package)), '--detach-sign',
         str(package)))


def pkgpath(pkgdir=None):
    """Yields the paths of the packages to be built."""

    text = check_output(PACKAGELIST, text=True, cwd=pkgdir)

    for line in text.split(linesep):
        yield Path(line)


@lru_cache()
def is_package(string):
    """Checks whether the path is a package."""

    if not isinstance(string, str):
        return is_package(str(string))

    match = PKG_REGEX.fullmatch(string)

    if match is None:
        raise NotAPackage()

    return match


@lru_cache()
def vercmp(version, other):
    """Compares package versions."""

    return int(check_output(('/usr/bin/vercmp', version, other), text=True))


@lru_cache()
def get_pkgbase_and_version(path):
    """Returns the pkgbase and version from the given file path."""

    command = ('/usr/bin/pacman', '-Qp', str(path))
    text = check_output(command, text=True).strip()
    pkgbase, version = text.split(maxsplit=1)
    return (pkgbase, Version(version))


@lru_cache()
def get_arch_and_compression(path):
    """Returns the architecture and file compression."""

    return is_package(path).groups()


class Version(str):
    """A package version."""

    def __hash__(self):
        return hash(str(self))

    def __eq__(self, other):
        return vercmp(self, other) == 0

    def __gt__(self, other):
        return vercmp(self, other) == 1

    def __lt__(self, other):
        return vercmp(self, other) == -1


class Package(PosixPath):
    """Package meta information."""

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

    def is_same_as(self, other):
        """Checks if package base and version match the other package."""
        return self.pkgbase == other.pkgbase and self.version == other.version


class Repository(NamedTuple):
    """Represents a repository."""

    name: str
    basedir: Path
    dbext: str
    sign: bool
    target: str

    @classmethod
    def from_config(cls, name, config):
        """Returns the repository from the given name and configuration."""
        basedir = Path(config['basedir'])
        dbext = config.get('dbext', '.db.tar.zst')
        sign = config.getboolean('sign')
        target = config.get('target')
        return cls(name, basedir, dbext, sign, target)

    @property
    def database(self):
        """Returns the database file name."""
        return self.name + self.dbext

    @property
    def dbpath(self):
        """Returns the path to the database file."""
        return self.basedir.joinpath(self.database)

    @property
    def packages(self):
        """Yields packages in the repository."""
        for path in self.basedir.glob(PKG_GLOB):
            if is_package(path) is not None:
                yield Package(path)

    @property
    def pkgbases(self):
        """Yields distinct package names."""
        return {pkg_info.pkgbase for pkg_info in self.packages}

    def _copy_pkg(self, package, sign):
        """Copies the package to the repository's base dir."""
        signature = pkgsig(package)

        if sign:
            if signature.is_file():
                LOGGER.warning('Package is already signed.')

            signpkg(package)

        with suppress(SameFileError):
            copy2(package, self.basedir)

        with suppress(SameFileError):
            copy2(signature, self.basedir)

    def packages_for_base(self, pkgbase):
        """Yields package files with the respective package information."""
        for path in self.basedir.glob(f'{pkgbase}-{PKG_GLOB}'):
            if is_package(path) is not None:
                yield Package(path)

    def isolate(self, package):
        """Removes other versions of the given package."""
        for other_package in self.packages_for_base(package.pkgbase):
            if package.is_same_as(other_package):
                LOGGER.info('Deleting %s.', other_package)
                package.unlink()
                signature = pkgsig(package)

                if signature.is_file():
                    signature.unlink()
                    LOGGER.debug('Deleted %s.', signature)
            else:
                LOGGER.debug('Keeping %s.', other_package)

    def add(self, package, *, sign=None, clean=False):
        """Adds the respective pacakge to the repo."""
        sign = self.sign if sign is None else sign
        self._copy_pkg(package, sign)

        repoadd = ['/usr/bin/repo-add', self.database, package.name]

        if sign:
            repoadd.append('--sign')

        check_call(repoadd, cwd=self.basedir)

        if clean:
            self.isolate(package)

    def rsync(self, target=None, *, delete=False):
        """Synchronizes the repository to the target."""
        target = self.target if target is None else target

        if target is None:
            LOGGER.error('No target specified.')
            return False

        command = ['/usr/bin/rsync', '-auv']
        source = str(self.basedir)

        if delete:
            command.append('--delete')
            source = source if source.endswith('/') else source + '/'

        command += [source, target]
        return check_call(command, cwd=self.basedir)
