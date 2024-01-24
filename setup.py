from setuptools import setup
from setuptools import find_packages

setup(
    name='dnsconfd',
    version='0.0.2',
    install_requires=[
        'dbus-python',
    ],
    packages=find_packages(),
    scripts=["bin/dnsconfd"],
)
