from types import SimpleNamespace
from unittest.mock import ANY, Mock

import pytest

from pdm.cli.commands import self_cmd


def mock_distribution(metadata, entry_points=()):
    entry_points = (SimpleNamespace(group=ep) for ep in entry_points)
    return SimpleNamespace(metadata=metadata, entry_points=entry_points)


DISTRIBUTIONS = [
    mock_distribution(
        {"Name": "foo", "Version": "1.0.0", "Summary": "Foo package"}, ["pdm.plugin"]
    ),
    mock_distribution(
        {"Name": "bar", "Version": "2.0.0", "Summary": "Bar package"}, ["pdm"]
    ),
    mock_distribution({"Name": "baz", "Version": "3.0.0", "Summary": "Baz package"}),
]


@pytest.fixture()
def mock_pip(monkeypatch):
    mocked = Mock()
    monkeypatch.setattr(self_cmd, "run_pip", mocked)
    return mocked


@pytest.fixture()
def mock_all_distributions(monkeypatch):
    monkeypatch.setattr(
        self_cmd, "_get_distributions", Mock(return_value=DISTRIBUTIONS)
    )


@pytest.mark.usefixtures("mock_all_distributions")
def test_self_list(invoke):
    result = invoke(["self", "list"])
    assert result.exit_code == 0, result.stderr
    packages = [line.split()[0] for line in result.stdout.splitlines()]
    assert packages == ["bar", "baz", "foo"]


@pytest.mark.usefixtures("mock_all_distributions")
def test_self_list_plugins(invoke):
    result = invoke(["self", "list", "--plugins"])
    assert result.exit_code == 0, result.stderr
    packages = [line.split()[0] for line in result.stdout.splitlines()]
    assert packages == ["bar", "foo"]


def test_self_add(invoke, mock_pip):
    result = invoke(["self", "add", "foo"])
    assert result.exit_code == 0, result.stderr
    mock_pip.assert_called_with(ANY, ["install", "foo"])

    result = invoke(["self", "add", "--pip-args", "--force-reinstall --upgrade", "foo"])
    assert result.exit_code == 0, result.stderr
    mock_pip.assert_called_with(
        ANY, ["install", "--force-reinstall", "--upgrade", "foo"]
    )


def test_self_remove(invoke, mock_pip, monkeypatch):
    def _mock_resolve(self, packages):
        return ["demo", "pytz"] if "demo" in packages else packages

    monkeypatch.setattr(
        self_cmd.RemoveCommand,
        "_resolve_dependencies_to_remove",
        _mock_resolve,
    )

    result = invoke(["self", "remove", "foo"])
    assert result.exit_code != 0

    result = invoke(["self", "remove", "-y", "demo"])
    assert result.exit_code == 0, result.stderr
    mock_pip.assert_called_with(ANY, ["uninstall", "-y", "demo", "pytz"])


@pytest.mark.parametrize(
    "args,expected",
    [
        (["self", "update"], ["install", "--upgrade", "pdm"]),
        (["self", "update", "--pre"], ["install", "--upgrade", "--pre", "pdm"]),
        (
            ["self", "update", "--head"],
            ["install", "--upgrade", f"pdm @ git+{self_cmd.PDM_REPO}@main"],
        ),
    ],
)
def test_self_update(invoke, mock_pip, args, expected):
    result = invoke(args)
    assert result.exit_code == 0, result.stderr
    mock_pip.assert_called_with(ANY, expected)