# PDM Scripts

Like `npm run`, with PDM, you can run arbitrary scripts or commands with local packages loaded.

## Arbitrary Scripts

```bash
pdm run flask run -p 54321
```

It will run `flask run -p 54321` in the environment that is aware of packages in your project environment.

## Single-file Scripts

+++ 2.16.0

PDM can run single-file scripts with [inline script metadata](https://peps.python.org/pep-0723/) specified by PEP 723.

The following is an example of a script with embedded metadata:

```python
# test_script.py
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "requests<3",
#   "rich",
# ]
# ///

import requests
from rich.pretty import pprint

resp = requests.get("https://peps.python.org/api/peps.json")
data = resp.json()
pprint([(k, v["title"]) for k, v in data.items()][:10])
```

When you run it with `pdm run test_script.py`, PDM will create a temporary environment with the specified dependencies installed and run the script:

```python
[
│   ('1', 'PEP Purpose and Guidelines'),
│   ('2', 'Procedure for Adding New Modules'),
│   ('3', 'Guidelines for Handling Bug Reports'),
│   ('4', 'Deprecation of Standard Modules'),
│   ('5', 'Guidelines for Language Evolution'),
│   ('6', 'Bug Fix Releases'),
│   ('7', 'Style Guide for C Code'),
│   ('8', 'Style Guide for Python Code'),
│   ('9', 'Sample Plaintext PEP Template'),
│   ('10', 'Voting Guidelines')
]
```
Add `--reuse-env` option if you want to reuse the environment created last time.
You can also add `[tool.pdm]` section to the script metadata to configure PDM. For example:

```python
# test_script.py
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "requests<3",
#   "rich",
# ]
#
# [[tool.pdm.source]]  # Use a custom index
# url = "https://mypypi.org/simple"
# name = "pypi"
# ///
```

Read the [specification](https://packaging.python.org/en/latest/specifications/inline-script-metadata/#inline-script-metadata) for more details.

## User Scripts

PDM also supports custom script shortcuts in the optional `[tool.pdm.scripts]` section of `pyproject.toml`.

!!! note "Confuse with `[project.scripts]`?"
    There is another field `[project.scripts]` in `pyproject.toml`, and the scripts can also be invoked with `pdm run`. It's used to define the console script entry points to be installed with the package. Therefore, the executables can only be run after the project itself is installed into the environment. That is to say, you must have `distribution = true`.

    In contrast, `[tool.pdm.scripts]` defines some tasks to be run in your project. It works for projects regardless of whether the `distribution` is `true` or `false`. The tasks are primarily for development and testing purposes and support more types and settings, as will be shown later., you can regard it as a replacement for `Makefile`. It doesn't require the project to be installed but requires the existence of a `pyproject.toml` file.

    See more explanations about `[project.scripts]` [here](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/#creating-executable-scripts).

You can then run `pdm run <script_name>` to invoke the script in the context of your PDM project. For example:

```toml
[tool.pdm.scripts]
start = "flask run -p 54321"
```

And then in your terminal:

```bash
$ pdm run start
Flask server started at http://127.0.0.1:54321
```

Any following arguments will be appended to the command:

```bash
$ pdm run start -h 0.0.0.0
Flask server started at http://0.0.0.0:54321
```

!!! note "Yarn-like script shortcuts"
    There is a builtin shortcut making all scripts available as root commands as long as the script does not conflict with any builtin or plugin-contributed command.
    Said otherwise, if you have a `start` script, you can run both `pdm run start` and `pdm start`.
    But if you have an `install` script, only `pdm run install` will run it, `pdm install` will still run the builtin `install` command.

PDM supports 4 types of scripts:

### `cmd`

Plain text scripts are regarded as normal command, or you can explicitly specify it:

```toml
[tool.pdm.scripts]
start = {cmd = "flask run -p 54321"}
```

In some cases, such as when wanting to add comments between parameters, it might be more convenient.
to specify the command as an array instead of a string:

```toml
[tool.pdm.scripts]
start = {cmd = [
    "flask",
    "run",
    # Important comment here about always using port 54321
    "-p", "54321"
]}
```

### `shell`

Shell scripts can be used to run more shell-specific tasks, such as pipeline and output redirecting.
This is basically run via `subprocess.Popen()` with `shell=True`:

```toml
[tool.pdm.scripts]
filter_error = {shell = "cat error.log|grep CRITICAL > critical.log"}
```

### `call`

The script can be also defined as calling a python function in the form `<module_name>:<func_name>`:

```toml
[tool.pdm.scripts]
foobar = {call = "foo_package.bar_module:main"}
```

The function can be supplied with literal arguments:

```toml
[tool.pdm.scripts]
foobar = {call = "foo_package.bar_module:main('dev')"}
```

### `composite`

This script kind execute other defined scripts:

```toml
[tool.pdm.scripts]
lint = "flake8"
test = "pytest"
all = {composite = ["lint", "test"]}
```

Running `pdm run all` will run `lint` first and then `test` if `lint` succeeded.

+++ 2.13.0

To override the default behavior and continue the execution of the remaining scripts after a failure,
set the `keep_going` option to `true`:

```toml
[tool.pdm.scripts]
lint = "flake8"
test = "pytest"
all.composite = ["lint", "test"]
all.keep_going = true
```

If `keep_going` set to `true` return code of composite script is either '0' if all succeeded or the code of last failed individual script.

You can also provide arguments to the called scripts:

```toml
[tool.pdm.scripts]
lint = "flake8"
test = "pytest"
all = {composite = ["lint mypackage/", "test -v tests/"]}
```

!!! note
    Argument passed on the command line are given to each called task.

You can also use the `composite` script to combine multiple commands:

```toml
[tool.pdm.scripts]
mytask.composite = [
    "echo 'Hello'",
    "echo 'World'"
]
```

## Script Options

### `env`

All environment variables set in the current shell can be seen by `pdm run` and will be expanded when executed.
Besides, you can also define some fixed environment variables in your `pyproject.toml`:

```toml
[tool.pdm.scripts]
start.cmd = "flask run -p 54321"
start.env = {FOO = "bar", FLASK_DEBUG = "1"}
```

Note how we use [TOML's syntax](https://github.com/toml-lang/toml) to define a composite dictionary.

!!! note "About environment variable substitution"
    Variables in script specifications can be substituted in all script types. In `cmd` scripts, only `${VAR}`
    syntax is supported on all platforms, however in `shell` scripts, the syntax is platform-dependent. For example,
    Windows cmd uses `%VAR%` while bash uses `$VAR`.

!!! note
    Environment variables specified on a composite task level will override those defined by called tasks.

### `env_file`

You can also store all environment variables in a dotenv file and let PDM read it:

```toml
[tool.pdm.scripts]
start.cmd = "flask run -p 54321"
start.env_file = ".env"
```

The variables within the dotenv file will *not* override any existing environment variables.
If you want the dotenv file to override existing environment variables use the following:

```toml
[tool.pdm.scripts]
start.cmd = "flask run -p 54321"
start.env_file.override = ".env"
```

!!! note "Environment variable loading order"
    Env vars loaded from different sources are loaded in the following order:

    1. OS environment variables
    2. Project environments such as `PDM_PROJECT_ROOT`, `PATH`, `VIRTUAL_ENV`, etc
    3. Dotenv file specified by `env_file`
    4. Env vars mapping specified by `env`

    Env vars from the latter sources will override those from the former sources.
    A dotenv file specified on a composite task level will override those defined by called tasks.

    An env var can contain a reference to another env var from the sources loaded before, for example:

    ```
    VAR=42
    FOO=hello-${VAR}
    ```
    will result in `FOO=hello-42`. The reference can also contain a default value with the syntax `${VAR:-default}`.

### `working_dir`

+++ 2.13.0

You can set the current working directory for the script:

```toml
[tool.pdm.scripts]
start.cmd = "flask run -p 54321"
start.working_dir = "subdir"
```

Relative paths are resolved against the project root.

+++ 2.20.2

To identify the original calling working directory, each script gets the environment variable `PDM_RUN_CWD` injected.

### `site_packages`

To make sure the running environment is properly isolated from the outer Python interpreter,
site-packages from the selected interpreter WON'T be loaded into `sys.path`, unless any of the following conditions holds:

1. The executable is from `PATH` but not inside the `__pypackages__` folder.
2. `-s/--site-packages` flag is following `pdm run`.
3. `site_packages = true` is in either the script table or the global setting key `_`.

Note that site-packages will always be loaded if running with PEP 582 enabled(without the `pdm run` prefix).

### Shared Options

If you want the options to be shared by all tasks run by `pdm run`,
you can write them under a special key `_` in `[tool.pdm.scripts]` table:

```toml
[tool.pdm.scripts]
_.env_file = ".env"
start = "flask run -p 54321"
migrate_db = "flask db upgrade"
```

Besides, inside the tasks, `PDM_PROJECT_ROOT` environment variable will be set to the project root.

### Arguments placeholder

By default, all user provided extra arguments are simply appended to the command (or to all the commands for `composite` tasks).

If you want more control over the user provided extra arguments, you can use the `{args}` placeholder.
It is available for all script types and will be interpolated properly for each:

```toml
[tool.pdm.scripts]
cmd = "echo '--before {args} --after'"
shell = {shell = "echo '--before {args} --after'"}
composite = {composite = ["cmd --something", "shell {args}"]}
```

will produce the following interpolations (those are not real scripts, just here to illustrate the interpolation):

```shell
$ pdm run cmd --user --provided
--before --user --provided --after
$ pdm run cmd
--before --after
$ pdm run shell --user --provided
--before --user --provided --after
$ pdm run shell
--before --after
$ pdm run composite --user --provided
cmd --something
shell --before --user --provided --after
$ pdm run composite
cmd --something
shell --before --after
```

You may optionally provide default values that will be used if no user arguments are provided:

```toml
[tool.pdm.scripts]
test = "echo '--before {args:--default --value} --after'"
```

will produce the following:

```shell
$ pdm run test --user --provided
--before --user --provided --after
$ pdm run test
--before --default --value --after
```

!!! note
    As soon a placeholder is detected, arguments are not appended anymore.
    This is important for `composite` scripts because if a placeholder
    is detected on one of the subtasks, none for the subtasks will have
    the arguments appended, you need to explicitly pass the placeholder
    to every nested command requiring it.

!!! note
    `call` scripts don't support the `{args}` placeholder as they have
    access to `sys.argv` directly to handle such complex cases and more.

### `{pdm}` placeholder

Sometimes you may have multiple PDM installations, or `pdm` installed with a different name. This
could for example occur in a CI/CD situation, or when working with different PDM versions in
different repos. To make your scripts more robust you can use `{pdm}` to use the PDM entrypoint
executing the script. This will expand to `{sys.executable} -m pdm`.

```toml
[tool.pdm.scripts]
whoami = { shell = "echo `{pdm} -V` was called as '{pdm} -V'" }
```

will produce the following output:

```shell
$ pdm whoami
PDM, version 0.1.dev2501+g73651b7.d20231115 was called as /usr/bin/python3 -m pdm -V

$ pdm2.8 whoami
PDM, version 2.8.0 was called as <snip>/venvs/pdm2-8/bin/python -m pdm -V
```

!!! note
    While the above example uses PDM 2.8, this functionality was introduced in the 2.10 series and only backported for the showcase.

## Show the List of Scripts

Use `pdm run --list/-l` to show the list of available script shortcuts:

```bash
$ pdm run --list
╭─────────────┬───────┬───────────────────────────╮
│ Name        │ Type  │ Description               │
├─────────────┼───────┼───────────────────────────┤
│ test_cmd    │ cmd   │ flask db upgrade          │
│ test_script │ call  │ call a python function    │
│ test_shell  │ shell │ shell command             │
╰─────────────┴───────┴───────────────────────────╯
```

You can add an `help` option with the description of the script, and it will be displayed in the `Description` column in the above output.

!!! note
    Tasks with a name starting with an underscore (`_`) are considered internal (helpers...) and are not shown in the listing.

## Pre & Post Scripts

Like `npm`, PDM also supports tasks composition by pre and post scripts, pre script will be run before the given task and post script will be run after.

```toml
[tool.pdm.scripts]
pre_compress = "{{ Run BEFORE the `compress` script }}"
compress = "tar czvf compressed.tar.gz data/"
post_compress = "{{ Run AFTER the `compress` script }}"
```

In this example, `pdm run compress` will run all these 3 scripts sequentially.

!!! note "The pipeline fails fast"
    In a pipeline of pre - self - post scripts, a failure will cancel the subsequent execution.

## Hook Scripts

Under certain situations PDM will look for some special hook scripts for execution:

- `post_init`: Run after `pdm init`
- `pre_install`: Run before installing packages
- `post_install`: Run after packages are installed
- `pre_lock`: Run before dependency resolution
- `post_lock`: Run after dependency resolution
- `pre_build`: Run before building distributions
- `post_build`: Run after distributions are built
- `pre_publish`: Run before publishing distributions
- `post_publish`: Run after distributions are published
- `pre_script`: Run before any script
- `post_script`: Run after any script
- `pre_run`: Run once before run script invocation
- `post_run`: Run once after run script invocation

!!! note
    Pre & post scripts can't receive any arguments.

!!! note "Avoid name conflicts"
    If there exists an `install` scripts under `[tool.pdm.scripts]` table, `pre_install`
    scripts can be triggered by both `pdm install` and `pdm run install`. So it is
    recommended to not use the preserved names.

!!! note
    Composite tasks can also have pre and post scripts.
    Called tasks will run their own pre and post scripts.

## Skipping scripts

Because, sometimes it is desirable to run a script but without its hooks or pre and post scripts,
there is a `--skip=:all` which will disable all hooks, pre and post.
There is also `--skip=:pre` and `--skip=:post` allowing to respectively
skip all `pre_*` hooks and all `post_*` hooks.

It is also possible to need a pre script but not the post one,
or to need all tasks from a composite tasks except one.
For those use cases, there is a finer grained `--skip` parameter
accepting a list of tasks or hooks name to exclude.

```bash
pdm run --skip pre_task1,task2 my-composite
```

This command will run the `my-composite` task and skip the `pre_task1` hook as well as the `task2` and its hooks.

You can also provide you skip list in `PDM_SKIP_HOOKS` environment variable
but it will be overridden as soon as the `--skip` parameter is provided.

There is more details on hooks and pre/post scripts behavior on [the dedicated hooks page](hooks.md).
