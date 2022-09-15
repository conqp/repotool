"""Miscellaneous functions."""

from collections import defaultdict
from configparser import ConfigParser
from json import load
from pathlib import Path
from typing import Iterable

from repotool.logging import LOGGER
from repotool.package import PackageFile
from repotool.repository import Repository


__all__ = ['list_repo', 'get_repositories', 'add_packages', 'rsync_repos']


def list_repo(repository: Repository) -> None:
    """Lists the packages of the given repository."""

    for package in repository.packages:
        print(*package)


def get_repositories(
        packages: Iterable[PackageFile],
        repository: str | None,
        mapping_file: Path,
        config: ConfigParser
) -> set[Repository]:
    """Return a set of repositories."""

    if repository:
        return {Repository.from_config(repository, config)}

    if not (memberships := get_memberships(mapping_file)):
        LOGGER.warning('No repo members configured in: %s', mapping_file)

    return {
        Repository.from_config(name, config)
        for package in packages
        for name in memberships[package.pkgbase]
    }


def add_packages(
        packages: Iterable[PackageFile],
        repositories: Iterable[Repository],
        sign: bool,
        clean: bool
) -> int:
    """Adds packages to a repo."""

    errors = 0

    for package in packages:
        try:
            add_package(package, repositories, sign=sign, clean=clean)
        except KeyError:
            LOGGER.error('No repositories configured for package: %s', package)
            errors += 1
        except KeyboardInterrupt:
            print()
            LOGGER.warning('Aborted by user.')
            errors += 1

    return errors


def rsync_repos(
        repositories: Iterable[Repository],
        target: str,
        delete: bool
) -> None:
    """Rsync the given repositories."""

    for repository in repositories:
        repository.rsync(target=target, delete=delete)


def add_package(
        package: PackageFile,
        repositories: Iterable[Repository],
        sign: bool,
        clean: bool
) -> None:
    """Add a package to repositories."""

    for repository in repositories:
        repository.add(package, sign=sign, clean=clean)


def get_memberships(path: Path) -> defaultdict[str, list[str]]:
    """Return a mapping of which repositories which packages belong to."""

    memberships = defaultdict(list)

    for repo, packages in get_repo_map(path).items():
        for package in packages:
            memberships[package].append(repo)

    return memberships


def get_repo_map(path: Path) -> dict:
    """Returns the target repository."""

    try:
        with path.open('r') as file:
            return load(file)
    except FileNotFoundError:
        LOGGER.warning('Repository map not found: %s', path)
        return {}
