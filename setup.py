import sys

# from distutils.core import setup, Extension
from setuptools import setup, find_packages, Extension


if sys.version_info.major < 3:
    raise RuntimeError('This module only supports python3')

rentry = Extension('pyrated.rentry',
                    sources = ['src/rentry.c'])

setup(
    name = 'pyrated',
    version = '1.0',
    #packages=find_packages('src/pyrated'),
    package_dir={'':'src'},

    # py_modules = ('src/pyrated',),
    description = 'The Python ratelimit daemon',
    ext_modules = [rentry],
    entry_points = {
        'console_scripts': ['pyrated=pyrated.server:main'],
    }
)