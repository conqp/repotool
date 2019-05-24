# repotool
An Arch Linux repository management tool

## Command line arguments

    usage: repotool [-h] [-c] [-s] [-r] [-t TARGET] [-d] [-v]
                    repository package [package ...]

    Manage Arch Linux packages and repositories.

    positional arguments:
      repository            the target repository
      package               the packages to add to the respository

    optional arguments:
      -h, --help            show this help message and exit
      -c, --clean           remove older versions of the package from the repo
      -s, --sign            sign the packages and repository
      -r, --rsync           rsync the repository to the configured location
      -t TARGET, --target TARGET
                            the rsync target
      -d, --delete          invoke rsync with delete flag
      -v, --verbose         enable verbose logging


## Configuration
`repotool` is being configured via `/etc/repotool.conf`:

    [MyRepository]
    basedir = /srv/my_repo
    sign = true
    target = user@my.server.com:/path/to/remote/repo

`basedir` specifies the local build repository's base directory.  
`sign` specifies the default signing policy and is optional.
`target` is the remote repository which will be rsync'ed to iff `-s` was specified and is optional.
