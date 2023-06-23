import sys
import shlex

from setuptools import setup, Extension
from setuptools.command.test import test as TestCommand

if sys.version_info.major < 3:
    raise RuntimeError('This module only supports python3')

ratelimit = Extension('pyrated._ratelimit',
                      sources=['pyrated/_ratelimit.c'])


class PyTest(TestCommand):
    user_options = [('pytest-args=', 'a', "Arguments to pass to pytest")]

    def initialize_options(self):
        TestCommand.initialize_options(self)
        self.pytest_args = ''

    def run_tests(self):
        # import here, cause outside the eggs aren't loaded
        import pytest
        errno = pytest.main(shlex.split(self.pytest_args))
        sys.exit(errno)


setup(
    name='pyrated',
    version='1.1',
    python_requires='>=3.7',

    packages=['pyrated'],

    description='The Python ratelimit daemon',
    ext_modules=[ratelimit],
    entry_points={
        'console_scripts': ['pyrated=pyrated.server:main'],
    },
    test_suite='pyrated.tests',
    tests_require=['pytest'],
    cmdclass={'test': PyTest},
)
