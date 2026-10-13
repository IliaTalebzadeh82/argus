"""Verify that the source package is installed by the project setup."""

from importlib.metadata import version

import argus


def test_installed_package_version_matches_imported_package() -> None:
    assert argus.__version__ == version("argus")
