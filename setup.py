from setuptools import setup
from setuptools import find_packages

setup(
    name='dnsconfd',
    version='1.1.2',
    install_requires=[
        'dbus-python',
        'pyyaml'
    ],
    packages=find_packages(),
    scripts=["bin/dnsconfd"],
)
