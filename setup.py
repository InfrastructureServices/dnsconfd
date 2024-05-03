from setuptools import setup
from setuptools import find_packages

setup(
    name='dnsconfd',
    version='0.0.5',
    install_requires=[
        'dbus-python',
        'pyyaml'
    ],
    packages=find_packages(),
    scripts=["bin/dnsconfd"],
)
