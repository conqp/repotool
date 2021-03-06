"""Miscellaneous functions."""

from argparse import ArgumentParser, Namespace
from collections import defaultdict
from configparser import ConfigParser
from json import load
from logging import DEBUG, INFO, basicConfig
from pathlib import Path
from sys import exit    # pylint: disable=W0622
from typing import Iterable, Iterator

from repotool.logging import LOG_FORMAT, LOGGER
from repotool.package import Package
from repotool.repository import Repository


__all__ = ['main']


CONFIG_FILE = Path('/etc/repotool.conf')
DESCRIPTION = 'Manage Arch Linux packages and repositories.'
MAPPING_FILE = Path('/etc/repotool.json')


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


def get_args() -> Namespace:
    """Parses and returns the command line arguments."""

    parser = ArgumentParser(description=DESCRIPTION)
    parser.add_argument(
        'package', type=Package, nargs='*',
        help='the packages to add to the respository')
    parser.add_argument(
        '-R', '--repository', metavar='name', help='the target repository')
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
