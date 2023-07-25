"""Command line interface."""

from argparse import ArgumentParser, Namespace
from configparser import ConfigParser
from logging import DEBUG, INFO, basicConfig
from pathlib import Path

from repotool.functions import list_repo
from repotool.functions import get_repositories
from repotool.functions import add_packages
from repotool.functions import rsync_repos
from repotool.logging import LOG_FORMAT, LOGGER
from repotool.package import PackageFile
from repotool.repository import Repository


__all__ = ["main"]


CONFIG_FILE = Path("/etc/repotool.conf")
DESCRIPTION = "Manage Arch Linux packages and repositories."
MAPPING_FILE = Path("/etc/repotool.json")


def get_args() -> Namespace:
    """Parses and returns the command line arguments."""

    parser = ArgumentParser(description=DESCRIPTION)
    parser.add_argument(
        "package",
        type=PackageFile,
        nargs="*",
        help="the packages to add to the repository",
    )
    parser.add_argument(
        "-R", "--repository", metavar="name", help="the target repository"
    )
    parser.add_argument(
        "-c",
        "--clean",
        action="store_true",
        help="remove other versions of the package from the repo",
    )
    parser.add_argument(
        "-d", "--delete", action="store_true", help="invoke rsync with delete flag"
    )
    parser.add_argument(
        "-f",
        "--config-file",
        type=Path,
        default=CONFIG_FILE,
        metavar="file",
        help="config file to read",
    )
    parser.add_argument(
        "-m",
        "--mapping-file",
        type=Path,
        default=MAPPING_FILE,
        metavar="file",
        help="package / repo mapping file to read",
    )
    parser.add_argument(
        "-r",
        "--rsync",
        action="store_true",
        help="rsync the repository to the configured location",
    )
    parser.add_argument(
        "-s", "--sign", action="store_true", help="sign the packages and repository"
    )
    parser.add_argument("-t", "--target", metavar="target", help="the rsync target")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="enable verbose logging"
    )
    return parser.parse_args()


def main() -> int:
    """Main program."""

    args = get_args()
    basicConfig(level=DEBUG if args.verbose else INFO, format=LOG_FORMAT)
    config = ConfigParser()

    if not config.read(args.config_file):
        LOGGER.warning("Unable to read config file: %s", args.config_file)

    if args.repository and not args.package and not args.rsync:
        list_repo(Repository.from_config(args.repository, config))
        return 0

    repositories = get_repositories(
        args.package, args.repository, args.mapping_file, config
    )
    error = add_packages(args.package, repositories, sign=args.sign, clean=args.clean)

    if args.rsync:
        rsync_repos(repositories, args.target, args.delete)

    return error
