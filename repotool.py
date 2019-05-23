"""Manage Arch Linux repositories."""

from contextlib import suppress
from os import linesep
from pathlib import Path
from shutil import SameFileError, copy2
from subprocess import check_call, check_output
from typing import NamedTuple


__all__ = ['pkgsig', 'signpkg', 'pkgpath', 'Repository']


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

    def add(self, package, sign=None):
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

        return check_call(repoadd, cwd=self.basedir)

    def rsync(self, target=None, *, delete=None):
        """Synchronizes the repository to the target."""
        target = self.target if target is None else target

        if target is None:
            return None

        delete = target.endswith('/') if delete is None else delete
        command = ['/usr/bin/rsync']

        if delete:
            command.append('--delete')

        command += ['./', target]
        return check_call(command, cwd=self.basedir)
