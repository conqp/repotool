"""Representation of repositories."""

from __future__ import annotations
from configparser import ConfigParser
from contextlib import suppress
from pathlib import Path
from shutil import SameFileError, copy2
from subprocess import check_call
from typing import Iterator, NamedTuple, Optional

from repotool.logging import LOGGER
from repotool.package import GLOB
from repotool.package import Package
from repotool.package import is_package
from repotool.package import sign as sign_package
from repotool.package import signature


__all__ = ['Repository']


class Repository(NamedTuple):
    """Represents a repository."""

    name: str
    basedir: Path
    dbext: str
    sign: bool
    target: Optional[str]

    @classmethod
    def from_config(cls, name: str, config: ConfigParser) -> Repository:
        """Returns the repository from the given name and configuration."""
        return cls(
            name,
            Path(config.get(name, 'basedir')),
            config.get(name, 'dbext', fallback='.db.tar.zst'),
            config.getboolean(name, 'sign', fallback=True),
            config.get(name, 'target', fallback=None)
        )

    @property
    def database(self):
        """Returns the database file name."""
        return self.name + self.dbext

    @property
    def packages(self):
        """Yields packages in the repository."""
        for path in self.basedir.glob(GLOB):
            if is_package(path) is not None:
                yield Package(path)

    @property
    def pkgbases(self):
        """Yields distinct package names."""
        return {pkg_info.pkgbase for pkg_info in self.packages}

    def _copy_pkg(self, package: Package, sign: bool) -> None:
        """Copies the package to the repository's base dir."""
        sigfile = signature(package)

        if sign:
            if sigfile.is_file():
                LOGGER.warning('Package is already signed.')

            sign_package(package)

        with suppress(SameFileError):
            copy2(package, self.basedir)

        with suppress(SameFileError):
            copy2(sigfile, self.basedir)

    def packages_for_base(self, pkgbase: str) -> Iterator[Package]:
        """Yields package files with the respective package information."""
        for path in self.basedir.glob(f'{pkgbase}-{GLOB}'):
            if is_package(path) is not None:
                yield Package(path)

    def isolate(self, package: Package) -> None:
        """Removes other versions of the given package."""
        for other_package in self.packages_for_base(package.pkgbase):
            if other_package.is_other_version_of(package):
                LOGGER.info('Deleting %s.', other_package)
                other_package.unlink()

                if (sigfile := signature(other_package)).is_file():
                    sigfile.unlink()
                    LOGGER.debug('Deleted %s.', sigfile)
            else:
                LOGGER.debug('Keeping %s.', other_package)

    def add(self, package: Package, *, sign: bool = False,
            clean: bool = False) -> None:
        """Adds the respective pacakge to the repo."""
        sign = sign or self.sign
        self._copy_pkg(package, sign)

        repoadd = ['/usr/bin/repo-add', self.database, package.name]

        if sign:
            repoadd.append('--sign')

        check_call(repoadd, cwd=self.basedir)

        if clean:
            self.isolate(package)

    def rsync(self, target: Optional[str] = None, *,
              delete: bool = False) -> int:
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
