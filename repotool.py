"""Manage Arch Linux repositories."""

from argparse import ArgumentParser
from configparser import ConfigParser
from contextlib import suppress
from functools import lru_cache
from logging import DEBUG, INFO, basicConfig, getLogger
from os import linesep
from pathlib import Path, PosixPath
from re import compile  # pylint: disable=W0622
from shutil import SameFileError, copy2
from subprocess import check_call, check_output
from sys import exit    # pylint: disable=W0622
from typing import NamedTuple


__all__ = [
    'pkgsig',
    'signpkg',
    'pkgpath',
    'vercmp',
    'main',
    'Version',
    'Package',
    'Repository'
]


DESCRIPTION = 'Manage Arch Linux packages and repositories.'
LOG_FORMAT = '[%(levelname)s] %(name)s: %(message)s'
LOGGER = getLogger(__file__)
PACKAGELIST = ('/usr/bin/makepkg', '--packagelist')
PKG_GLOB = '*.pkg.tar*'
PKG_REGEX = compile('^.*-(x86_64|i686|any)\\.pkg\\.tar(\\.[a-z]{2,3})?$')


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
    """Checks whether the path is a package and returns a regex match."""

    if not isinstance(string, str):
        return is_package(str(string))

    return PKG_REGEX.fullmatch(string)


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


def get_args():
    """Parses and returns the command line arguments."""

    parser = ArgumentParser(description=DESCRIPTION)
    parser.add_argument('repository', help='the target repository')
    parser.add_argument(
        'package', type=Package, nargs='*',
        help='the packages to add to the respository')
    parser.add_argument(
        '-c', '--clean', action='store_true',
        help='remove other versions of the package from the repo')
    parser.add_argument(
        '-s', '--sign', action='store_true',
        help='sign the packages and repository')
    parser.add_argument(
        '-r', '--rsync', action='store_true',
        help='rsync the repository to the configured location')
    parser.add_argument('-t', '--target', help='the rsync target')
    parser.add_argument(
        '-d', '--delete', action='store_true',
        help='invoke rsync with delete flag')
    parser.add_argument(
        '-v', '--verbose', action='store_true',
        help='enable verbose logging')
    return parser.parse_args()


def main():
    """Main program."""

    args = get_args()
    basicConfig(level=DEBUG if args.verbose else INFO, format=LOG_FORMAT)
    config = ConfigParser()
    config.read('/etc/repotool.conf')
    repo_config = config[args.repository]
    repository = Repository.from_config(args.repository, repo_config)

    if not args.package:
        for package in repository.packages:
            print(*package)

        exit(0)

    exit_code = 0

    for package in args.package:
        try:
            repository.add(package, sign=args.sign, clean=args.clean)
        except KeyboardInterrupt:
            print()
            LOGGER.warning('Skipped adding package %s.', package)
            exit_code += 1

    if args.rsync:
        try:
            repository.rsync(target=args.target, delete=args.delete)
        except KeyboardInterrupt:
            print()
            LOGGER.warning('Synchronization aborted by user.')
            exit_code += 1

    exit(exit_code)


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


class Package(PosixPath):
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

    def is_other_version_of(self, other):
        """Checks if the other package is considered
        another version of this pacakge.
        """
        if self.pkgbase == other.pkgbase:
            if self.version != other.version:
                return True

            if self.compression != other.compression:
                return True

        return False


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
            if other_package.is_other_version_of(package):
                LOGGER.info('Deleting %s.', other_package)
                other_package.unlink()

                if (signature := pkgsig(other_package)).is_file():
                    signature.unlink()
                    LOGGER.debug('Deleted %s.', signature)
            else:
                LOGGER.debug('Keeping %s.', other_package)

    def add(self, package, *, sign=None, clean=False):
        """Adds the respective pacakge to the repo."""
        sign = sign or self.sign
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
