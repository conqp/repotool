"""Manage Arch Linux repositories."""

from __future__ import annotations
from argparse import ArgumentParser, Namespace
from collections import defaultdict
from configparser import ConfigParser
from contextlib import suppress
from functools import lru_cache
from json import load
from logging import DEBUG, INFO, basicConfig, getLogger
from os import linesep
from pathlib import Path, PosixPath
from re import Match, fullmatch
from shutil import SameFileError, copy2
from subprocess import check_call, check_output
from sys import exit    # pylint: disable=W0622
from typing import Iterable, Iterator, NamedTuple, Optional, Tuple, Union


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


CONFIG_FILE = Path('/etc/repotool.conf')
DESCRIPTION = 'Manage Arch Linux packages and repositories.'
LOG_FORMAT = '[%(levelname)s] %(name)s: %(message)s'
LOGGER = getLogger(__file__)
MAPPING_FILE = Path('/etc/repotool.json')
PACKAGELIST = ('/usr/bin/makepkg', '--packagelist')
PKG_GLOB = '*.pkg.tar*'
PKG_REGEX = '^.*-(x86_64|i686|any)\\.pkg\\.tar(\\.[a-z]{2,3})?$'


def pkgsig(package: Path) -> Path:
    """Returns the path to the package's signature."""

    return Path(str(package) + '.sig')


def signpkg(package: Path) -> int:
    """Signs the respective pacakge."""

    return check_call(
        ('/usr/bin/gpg', '--output', str(pkgsig(package)), '--detach-sign',
         str(package)))


def pkgpath(pkgdir: Union[Path, str, None] = None) -> Iterator[Path]:
    """Yields the paths of the packages to be built."""

    text = check_output(PACKAGELIST, text=True, cwd=pkgdir)

    for line in text.split(linesep):
        yield Path(line)


@lru_cache()
def is_package(string: str) -> Match:
    """Checks whether the path is a package and returns a regex match."""

    if not isinstance(string, str):
        return is_package(str(string))

    return fullmatch(PKG_REGEX, string)


@lru_cache()
def vercmp(version: str, other: str) -> int:
    """Compares package versions."""

    return int(check_output(('/usr/bin/vercmp', version, other), text=True))


@lru_cache()
def get_pkgbase_and_version(path: Path) -> Tuple[str, Version]:
    """Returns the pkgbase and version from the given file path."""

    command = ('/usr/bin/pacman', '-Qp', str(path))
    text = check_output(command, text=True).strip()
    pkgbase, version = text.split(maxsplit=1)
    return (pkgbase, Version(version))


@lru_cache()
def get_arch_and_compression(path: Path) -> Tuple[str, str]:
    """Returns the architecture and file compression."""

    return is_package(path).groups()


def get_args() -> Namespace:
    """Parses and returns the command line arguments."""

    parser = ArgumentParser(description=DESCRIPTION)
    parser.add_argument(
        'package', type=Package, nargs='*',
        help='the packages to add to the respository')
    parser.add_argument('-R', '--repository', help='the target repository')
    parser.add_argument(
        '-c', '--clean', action='store_true',
        help='remove other versions of the package from the repo')
    parser.add_argument(
        '-d', '--delete', action='store_true',
        help='invoke rsync with delete flag')
    parser.add_argument(
        '-f', '--config-file', type=Path, default=CONFIG_FILE, metavar='file',
        help='config file to read')
    parser.add_argument(
        '-m', '--mapping-file', type=Path, default=MAPPING_FILE,
        metavar='file', help='packge / repo mapping file to read')
    parser.add_argument(
        '-r', '--rsync', action='store_true',
        help='rsync the repository to the configured location')
    parser.add_argument(
        '-s', '--sign', action='store_true',
        help='sign the packages and repository')
    parser.add_argument('-t', '--target', help='the rsync target')
    parser.add_argument(
        '-v', '--verbose', action='store_true',
        help='enable verbose logging')
    return parser.parse_args()


def get_repo_map(path: Path) -> dict:
    """Returns the target repository."""

    try:
        with path.open('r') as file:
            return load(file)
    except FileNotFoundError:
        return {}


def get_memberships(path: Path) -> dict[str, list[str]]:
    """Returns a mapping of which repositories packages belong to."""

    memberships = defaultdict(list)

    for repo, packages in get_repo_map(path).items():
        for package in packages:
            memberships[package].append(repo)

    return memberships


def get_repositories(package: Package, args: Namespace, config: ConfigParser,
                     memberships: dict) -> Iterator[Repository]:
    """Yields target repositories."""

    if args.repository:
        yield Repository.from_config(args.repository, config)
        return

    for name in memberships[package.pkgbase]:
        yield Repository.from_config(name, config)


def add_package(package: Package, repositories: Iterable[Repository],
                args: Namespace) -> bool:
    """Adds a package to a repository."""

    for repository in repositories:
        repository.add(package, sign=args.sign, clean=args.clean)

        if args.rsync:
            repository.rsync(target=args.target, delete=args.delete)


def main():
    """Main program."""

    args = get_args()
    basicConfig(level=DEBUG if args.verbose else INFO, format=LOG_FORMAT)
    config = ConfigParser()

    if not config.read(args.config_file):
        LOGGER.warning('Unable to read config file: %s', args.config_file)

    if not (memberships := get_memberships(args.mapping_file)):
        LOGGER.warning('No repo members configured in: %s', args.mapping_file)

    if args.repository and not args.package:
        repository = Repository.from_config(repository, config)

        for package in repository.packages:
            print(*package)

        exit(0)

    returncode = 0

    for package in args.package:
        repositories = get_repositories(package, args, config, memberships)

        try:
            add_package(package, repositories, args)
        except KeyError:
            LOGGER.error('No repositories configured for package: %s', package)
            returncode += 1
            continue
        except KeyboardInterrupt:
            print()
            LOGGER.warning('Aborted by user.')
            returncode += 1
            continue

    exit(returncode)


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


class Repository(NamedTuple):
    """Represents a repository."""

    name: str
    basedir: Path
    dbext: str
    sign: bool
    target: str

    @classmethod
    def from_config(cls, name: str, config: ConfigParser) -> Repository:
        """Returns the repository from the given name and configuration."""
        return cls(
            name,
            Path(config.get(name, 'basedir')),
            config.get(name, 'dbext', fallback='.db.tar.zst'),
            config.getboolean(name, 'sign'),
            config.get(name, 'target')
        )

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

    def _copy_pkg(self, package: Package, sign: bool) -> None:
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

    def packages_for_base(self, pkgbase: str) -> Iterator[Package]:
        """Yields package files with the respective package information."""
        for path in self.basedir.glob(f'{pkgbase}-{PKG_GLOB}'):
            if is_package(path) is not None:
                yield Package(path)

    def isolate(self, package: Package) -> None:
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
