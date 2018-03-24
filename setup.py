from os import path
from io import open
from setuptools import setup, find_packages

with open('README.rst', 'rb') as f:
    readme = f.read().decode('utf-8')

curr_dir = path.abspath(path.dirname(__file__))
with open(path.join(curr_dir, 'requirements.txt'), encoding='utf-8') as f:
    all_reqs = f.read().split('\n')

setup(
    name='airtiler',
    packages=find_packages(exclude=('tests', 'docs')),
    version='1.0.0',
    description='The airtiler generates training / test data for neural networks by downloading buildings from vector '
                'data from OpenStreetMap and the corresponding satellite images from Microsoft Bing Maps.',
    long_description=readme,
    author='Martin Boos',
    url='https://github.com/mnboos/airtiler',
    license='MIT',
    keywords='machinelearning',
    install_requires=all_reqs,
    entry_points={
        'console_scripts': ['airtiler=airtiler.__init__:main'],
    },
)
