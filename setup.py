from setuptools import setup

with open("README.md", "r") as f:
    long_description = f.read()

setup(
    name="pylitterbot",
    version="0.1.0",
    description="Python package for controlling a Litter-Robot Connect self-cleaning litter box",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Nathan Spencer",
    author_email="natekspencer@gmail.com",
    url="https://github.com/natekspencer/pylitterbot",
    license="Licensed under the MIT license. See LICENSE file for details",
    packages=["pylitterbot"],
    package_dir={"pylitterbot": "pylitterbot"},
    install_requires=["requests", "requests_oauthlib", "PyJWT"],
)
