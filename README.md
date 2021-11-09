# repotool
An Arch Linux repository management tool

## Command line arguments

```
usage: repotool [-h] [-R name] [-c] [-d] [-f file] [-m file] [-r] [-s] [-t target] [-v] [package ...]

Manage Arch Linux packages and repositories.

positional arguments:
  package               the packages to add to the respository

optional arguments:
  -h, --help            show this help message and exit
  -R name, --repository name
                        the target repository
  -c, --clean           remove other versions of the package from the repo
  -d, --delete          invoke rsync with delete flag
  -f file, --config-file file
                        config file to read
  -m file, --mapping-file file
                        packge / repo mapping file to read
  -r, --rsync           rsync the repository to the configured location
  -s, --sign            sign the packages and repository
  -t target, --target target
                        the rsync target
  -v, --verbose         enable verbose logging
```

## Configuration
`repotool` is being configured via `/etc/repotool.conf`:

```ini
[MyRepository]
basedir = /srv/my_repo
dbext = .db.tar.zst
sign = true
target = user@my.server.com:/path/to/remote/repo
```

`basedir` specifies the local build repository's base directory.  
`dbext` is the database file extension. This is optional and defaults to `.db.tar.zst`.  
`sign` specifies the default signing policy and is optional.  
`target` is the remote repository which will be rsync'ed to iff `-s` was specified and is optional.
