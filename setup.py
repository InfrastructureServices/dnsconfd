from setuptools import setup
from setuptools import find_packages

setup(
    name='dnsconfd',
    version='1.5.0',
    install_requires=[
        'dbus-python',
        'pyyaml'
    ],
    packages=find_packages(exclude=["unittests*"]),
    scripts=["bin/dnsconfd"],
)
