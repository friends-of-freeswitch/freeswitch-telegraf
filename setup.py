#!/usr/bin/env python
# vim: tabstop=4 softtabstop=4 shiftwidth=4 textwidth=80 smarttab expandtab
"""
FreeSWITCH Telegraf Metric Collector
"""
try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup


README = open('README.rst').read()
DOCLINK = """
Documentation
-------------

The full documentation is at http:///."""

setup(
    name='fstelegraf',
    version='0.0.1',
    description='FreeSWITCH Telegraf Input Plugin',
    long_description=README + '\n\n' + DOCLINK + '\n\n',
    author='Moises Silva',
    author_email='moises.silva@gmail.com',
    url='https://github.com/moises-silva/freeswitch-telegraf',
    packages=[
        'fstelegraf',
    ],
    install_requires=['greenswitch'],
    dependency_links=[
        'git+https://github.com/EvoluxBR/greenswitch.git#egg=greenswitch'
    ],
    license='MIT',
    zip_safe=False,  # For easy debugging, always extract the python egg
    classifiers=[
        'Programming Language :: Python :: 2.7',
    ],
    entry_points={
        'console_scripts': [
            'freeswitch-telegraf = fstelegraf.collector:main'
        ],
    }
)
