from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

# get version from __version__ variable in sitiame_core/__init__.py
from sitiame_core import __version__ as version

setup(
	name="sitiame_core",
	version=version,
	description="Sitiame Capital - Inscription entreprise sur ERPNext",
	author="Sitiame Capital",
	author_email="contact@sitiame-capital.com",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
)
