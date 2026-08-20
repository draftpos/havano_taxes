from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

# get version from __version__ variable in havano_taxes/__init__.py
from havano_taxes import __version__ as version

setup(
    name="havano_taxes",
    version=version,
    description="Item-level tax resolution for ERPNext v15 — VAT, ZERO RATED, EXEMPT on one invoice with ZIMRA fiscalisation support",
    author="Havano",
    author_email="dev@havano.cloud",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
