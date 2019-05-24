"""Manage Arch Linux repositories."""

from contextlib import suppress
from logging import getLogger
from os import linesep
from pathlib import Path
from shutil import SameFileError, copy2
from subprocess import check_call, check_output
from typing import NamedTuple


__all__ = ['pkgsig', 'signpkg', 'pkgpath', 'Repository']


LOGGER = getLogger(__file__)
PACKAGELIST = ('/usr/bin/makepkg', '--packagelist')


def pkgsig(package):
    """Returns the path to the package's signature."""

    return Path(str(package) + '.sig')


def signpkg(package):
    """Signs the respective pacakge."""

    signature = pkgsig(package)
    command = ('/usr/bin/gpg', '--output', str(signature),
               '--detach-sign', str(package))
    return check_call(command)


def pkgpath(pkgdir=None):
    """Yields the paths of the packages to be built."""

    if pkgdir is None:
        text = check_output(PACKAGELIST, text=True)
    else:
        text = check_output(PACKAGELIST, text=True, cwd=pkgdir)

    for line in text.split(linesep):
        yield Path(line)


class PkgInfo(NamedTuple):
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
        items = text.split(maxsplit=1)
        return cls(*items)


class Repository(NamedTuple):
    """Represents a repository."""

    name: str
    basedir: Path
    sign: bool
    target: str

    @classmethod
    def from_config(cls, name, config):
        """Returns the repository from the given name and configuration."""
        basedir = Path(config['basedir'])
        sign = config.getboolean('sign')
        target = config.get('target')
        return cls(name, basedir, sign, target)

    @property
    def database(self):
        """Returns the database file name."""
        return self.name + '.db.tar.xz'

    @property
    def dbpath(self):
        """Returns the path to the database file."""
        return self.basedir.joinpath(self.database)

    @property
    def packages(self):
        """Yields packages in the repository."""
        return self.basedir.glob('*.pkg.tar.xz')

    @property
    def pkgbases(self):
        """Yields distinct package names."""
        return {PkgInfo.from_file(pkg).pkgbase for pkg in self.packages}

    def add(self, package, *, sign=None, clean=False):
        """Adds the respective pacakge to the repo."""
        sign = self.sign if sign is None else sign

        if sign and not pkgsig(package).is_file():
            signpkg(package)

        with suppress(SameFileError):
            copy2(package, self.basedir)

        signature = pkgsig(package)

        if signature.is_file():
            with suppress(SameFileError):
                copy2(signature, self.basedir)

        repoadd = ['/usr/bin/repo-add', self.database, package.name]

        if sign:
            repoadd.append('--sign')

        check_call(repoadd, cwd=self.basedir)

        if clean:
            self.isolate(PkgInfo.from_file(package))

    def isolate(self, pkg_info):
        """Removes other versions of the given package."""
        for package in self.basedir.glob(f'{pkg_info.pkgbase}-*.pkg.tar.xz'):
            current_pkg_info = PkgInfo.from_file(package)

            if current_pkg_info == pkg_info:
                LOGGER.debug('Keeping %s.', current_pkg_info)
                continue

            LOGGER.info('Deleting %s.', current_pkg_info)
            package.unlink()
            LOGGER.debug('Deleted %s.', package)
            signature = pkgsig(package)

            if signature.is_file():
                signature.unlink()
                LOGGER.debug('Deleted %s.', signature)

    def rsync(self, target=None, *, delete=False):
        """Synchronizes the repository to the target."""
        target = self.target if target is None else target

        if target is None:
            return None

        command = ['/usr/bin/rsync', '-auv']
        source = str(self.basedir)

        if delete:
            command.append('--delete')
            source = source if source.endswith('/') else source + '/'

        command += [source, target]
        return check_call(command, cwd=self.basedir)
