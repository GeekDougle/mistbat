# setup.py
from setuptools import setup, find_packages

with open("requirements.txt") as f:
    requirements = f.read().splitlines()

setup(
    name="mistbat",
    version="0.2.0",
    packages=find_packages(),
    install_requires=requirements,
    # Add other metadata like author, description, etc.
)
