from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from typing import Any

from pdm import termui
from pdm.cli.actions import get_latest_pdm_version_from_pypi
from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import verbose_option
from pdm.cli.utils import PackageNode, build_dependency_graph
from pdm.compat import Distribution
from pdm.environments import BareEnvironment
from pdm.models.markers import EnvSpec
from pdm.models.working_set import WorkingSet
from pdm.project import Project
from pdm.utils import is_in_zipapp, normalize_name, parse_version

PDM_REPO = "https://github.com/pdm-project/pdm"


def list_distributions(plugin_only: bool = False) -> list[Distribution]:
    result: list[Distribution] = []
    working_set = WorkingSet()
    for dist in working_set.values():
        if not plugin_only or any(ep.group in ("pdm", "pdm.plugin") for ep in dist.entry_points):
            result.append(dist)
    return sorted(result, key=lambda d: d.metadata.get("Name", "UNKNOWN"))


def run_pip(project: Project, args: list[str]) -> subprocess.CompletedProcess[str]:
    if project.config["use_uv"]:
        if "--upgrade-strategy" in args:
            # uv doesn't support this option
            args[(i := args.index("--upgrade-strategy")) : i + 2] = []
        run_args = [*project.core.uv_cmd, "pip", *args, "--python", sys.executable]
    else:
        env = BareEnvironment(project)
        project.environment = env
        run_args = [*env.pip_command, *args]
    project.core.ui.echo(f"Running pip command: {run_args}", verbosity=termui.Verbosity.DETAIL)

    result = subprocess.run(
        run_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
        text=True,
    )
    project.core.ui.echo(
        f"Run pip returns status {result.returncode}: {result.stdout}", verbosity=termui.Verbosity.DEBUG
    )
    return result


class Command(BaseCommand):
    """Manage the PDM program itself (previously known as plugin)"""

    arguments = (verbose_option,)
    name = "self"

    @classmethod
    def register_to(
        cls,
        subparsers: argparse._SubParsersAction,
        name: str | None = None,
        **kwargs: Any,
    ) -> None:
        return super().register_to(subparsers, name, aliases=["plugin"], **kwargs)

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        subparsers = parser.add_subparsers(title="commands", metavar="")
        ListCommand.register_to(subparsers)
        if not is_in_zipapp():
            AddCommand.register_to(subparsers)
            RemoveCommand.register_to(subparsers)
            UpdateCommand.register_to(subparsers)
        parser.set_defaults(search_parent=False)
        self.parser = parser

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        self.parser.print_help()


class ListCommand(BaseCommand):
    """List all packages installed with PDM"""

    arguments = (verbose_option,)
    name = "list"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--plugins", action="store_true", help="List plugins only")

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        distributions = list_distributions(plugin_only=options.plugins)
        echo = project.core.ui.echo
        if not distributions:
            # This should not happen when plugin_only is False
            echo("No plugin is installed with PDM", err=True)
            sys.exit(1)
        echo("Installed packages:", err=True)
        rows = []
        for dist in distributions:
            rows.append(
                (
                    f"[success]{dist.metadata.get('Name')}[/]",
                    f"[warning]{dist.metadata.get('Version')}[/]",
                    dist.metadata.get("Summary", ""),
                ),
            )
        project.core.ui.display_columns(rows)


class AddCommand(BaseCommand):
    """Install packages to the PDM's environment"""

    arguments = (verbose_option,)
    name = "add"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--pip-args",
            help="Arguments that will be passed to pip install",
            default="",
        )
        parser.add_argument(
            "packages",
            nargs="+",
            help="Specify one or many package names, each package can have a version specifier",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        pip_args = ["install", *shlex.split(options.pip_args), *options.packages]

        try:
            with project.core.ui.open_spinner(f"Installing packages: {options.packages}"):
                run_pip(project, pip_args)
        except subprocess.CalledProcessError as e:
            project.core.ui.echo("[error]Installation failed:[/]\n" + e.output, err=True)
            sys.exit(1)
        else:
            project.core.ui.echo("[success]Installation succeeds.[/]")


class RemoveCommand(BaseCommand):
    """Remove packages from PDM's environment"""

    arguments = (verbose_option,)
    name = "remove"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--pip-args",
            help="Arguments that will be passed to pip uninstall",
            default="",
        )
        parser.add_argument("-y", "--yes", action="store_true", help="Answer yes on the question")
        parser.add_argument("packages", nargs="+", help="Specify one or many package names")

    def _resolve_dependencies_to_remove(self, packages: list[str]) -> list[str]:
        """Perform a BFS to find all unneeded dependencies"""
        result: set[str] = set()
        to_resolve = list(packages)

        ws = WorkingSet()
        graph = build_dependency_graph(ws, env_spec=EnvSpec.current())
        while to_resolve:
            temp: list[PackageNode] = []
            for name in to_resolve:
                key = normalize_name(name)
                if key in ws:
                    result.add(key)
                package = PackageNode(key, "0.0.0", {})
                if package not in graph:
                    continue
                for dep in graph.iter_children(package):
                    temp.append(dep)
                graph.remove(package)

            to_resolve.clear()
            for dep in temp:
                if not any(graph.iter_parents(dep)) and dep.name != "pdm":
                    to_resolve.append(dep.name)

        return sorted(result)

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        packages_to_remove = self._resolve_dependencies_to_remove(options.packages)
        if not packages_to_remove:
            project.core.ui.echo("No package to remove.", err=True)
            sys.exit(1)
        if not (options.yes or termui.confirm(f"Will remove: {packages_to_remove}, continue?", default=True)):
            return
        pip_args = ["uninstall", "-y", *shlex.split(options.pip_args), *packages_to_remove]

        try:
            with project.core.ui.open_spinner(f"Uninstalling packages: [success]{', '.join(options.packages)}[/]"):
                run_pip(project, pip_args)
        except subprocess.CalledProcessError as e:
            project.core.ui.echo("[error]Uninstallation failed:[/]\n" + e.output, err=True)
            sys.exit(1)
        else:
            project.core.ui.echo("[success]Uninstallation succeeds.[/]")


class UpdateCommand(BaseCommand):
    """Update PDM itself"""

    arguments = (verbose_option,)
    name = "update"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--head",
            action="store_true",
            help="Update to the latest commit on the main branch",
        )
        parser.add_argument(
            "--pre",
            help="Update to the latest prerelease version",
            action="store_true",
        )
        parser.add_argument(
            "--no-frozen-deps",
            action="store_false",
            dest="frozen_deps",
            default=True,
            help="Do not install frozen dependency versions",
        )
        parser.add_argument(
            "--pip-args",
            help="Additional arguments that will be passed to pip install",
            default="",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        from pdm.__version__ import __version__, read_version

        locked = "[locked]" if options.frozen_deps else ""

        if options.head:
            package = f"pdm{locked} @ git+{PDM_REPO}@main"
            version: str | None = "HEAD"
        else:
            version = get_latest_pdm_version_from_pypi(project, options.pre)
            assert version is not None, "No version found"
            if parse_version(__version__) >= parse_version(version):
                project.core.ui.echo(f"Already up-to-date: [primary]{__version__}[/]")
                return
            package = f"pdm{locked}=={version}"
        pip_args = ["install", "--upgrade", "--upgrade-strategy", "eager", *shlex.split(options.pip_args), package]
        try:
            with project.core.ui.open_spinner(f"Updating pdm to version [primary]{version}[/]"):
                run_pip(project, pip_args)
        except subprocess.CalledProcessError as e:
            project.core.ui.echo(
                f"[error]Installing version [primary]{version}[/] failed:[/]\n" + e.output,
                err=True,
            )
            sys.exit(1)
        else:
            project.core.ui.echo(f"[success]Successfully installed version [primary]{version}[/][/]")
            project.core.ui.echo(f"See what's new in this version: [link]{PDM_REPO}/releases/tag/{version}[/]")
            # Update the version value to avoid check update print wrong message
            project.core.version = read_version()
