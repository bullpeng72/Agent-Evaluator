"""
Setup script for agent-evaluator package.
This file provides backward compatibility with older pip versions.
For modern installations, pyproject.toml is preferred.
"""
from setuptools import setup, find_packages

if __name__ == "__main__":
    setup(
        name="agent-evaluator",
        packages=find_packages(),
        include_package_data=True,
    )
