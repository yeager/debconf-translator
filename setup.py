from setuptools import setup, find_packages

setup(
    name="debconf-translator",
    version="0.1.0",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "debconf-translator=debconf_translator.cli:main",
        ],
    },
)
