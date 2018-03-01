from io import open
from setuptools import setup

with open('README.rst', 'rb') as f:
    readme = f.read().decode('utf-8')

setup(
    name='airtiler',
    packages=['airtiler'],
    version='0.2.0',
    description='The airtiler generates training / test data for neural networks by downloading buildings from vector '
                'data from OpenStreetMap and the corresponding satellite images from Microsoft Bing Maps.',
    long_description=readme,
    author='Martin Boos',
    url='https://github.com/mnboos/airtiler',
    license='MIT',
    keywords='machinelearning'
)
