"""Manage Arch Linux repositories."""

from contextlib import suppress
from logging import getLogger
from os import linesep
from pathlib import Path
from shutil import SameFileError, copy2
from subprocess import check_call, check_output
from typing import NamedTuple


__all__ = [
    'pkgsig',
    'signpkg',
    'pkgpath',
    'vercmp',
    'PackageInfo',
    'Repository'
]


LOGGER = getLogger(__file__)
PACKAGELIST = ('/usr/bin/makepkg', '--packagelist')
PKG_GLOB = '*.pkg.tar*'
PKG_REGEX = compile('^(.*)\\.pkg\\.tar(\\.[a-z]{2,3})?$')


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


def vercmp(version, other):
    """Compares package versions."""

    return int(check_output(('/usr/bin/vercmp', version, other), text=True))


class PackageInfo(NamedTuple):
    """Package meta information."""

    pkgbase: str
    version: str

    def __str__(self):
        """Returns the pacakge base and version."""
        return f'{self.pkgbase} {self.version}'

    @classmethod
    def from_file(cls, path):
        """Returns the package info from the given file path."""
        command = ('/usr/bin/pacman', '-Qp', str(path))
        text = check_output(command, text=True).strip()
        pkgbase, version = text.split(maxsplit=1)
        return cls(pkgbase, version)


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
        for candidate in self.basedir.glob(PKG_GLOB):
            if PKG_REGEX.fullmatch(str(candidate)) is not None:
                yield candidate

    @property
    def pkgbases(self):
        """Yields distinct package names."""
        return {PackageInfo.from_file(pkg).pkgbase for pkg in self.packages}

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

    def _package_files(self, pkgbase):
        """Yields package files with the respective package information."""
        for candidate in self.basedir.glob(f'{pkgbase}-*{PKG_GLOB}'):
            if PKG_REGEX.fullmatch(str(candidate)) is not None:
                yield candidate

    def isolate(self, pkg_info):
        """Removes other versions of the given package."""
        for package in self._package_files(pkg_info.pkgbase):
            current_pkg_info = PackageInfo.from_file(package)

            if current_pkg_info != pkg_info:
                LOGGER.info('Deleting %s.', current_pkg_info)
                package.unlink()
                signature = pkgsig(package)

                if signature.is_file():
                    signature.unlink()
                    LOGGER.debug('Deleted %s.', signature)
            else:
                LOGGER.debug('Keeping %s.', current_pkg_info)

    def add(self, package, *, sign=None, clean=False):
        """Adds the respective pacakge to the repo."""
        sign = self.sign if sign is None else sign
        self._copy_pkg(package, sign)

        repoadd = ['/usr/bin/repo-add', self.database, package.name]

        if sign:
            repoadd.append('--sign')

        check_call(repoadd, cwd=self.basedir)

        if clean:
            self.isolate(PackageInfo.from_file(package))

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
