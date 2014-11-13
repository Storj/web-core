from distutils.core import setup

try:
    longdescription = open('README.md').read()
except EnvironmentError:
    longdescription = 'Core manager of MetaDisk node services.'

setup(
    name='web-core',
    version='0.3',
    author='Storj',
    author_email='storj@example.com',
    packages=['webcore', ],
    scripts=[],
    url='https://github.com/Storj/web-core',
    license='MIT',
    description='Core manager of MetaDisk node services.',
    long_description=longdescription,
    install_requires=[
        'pycrypto >= 2.6.1',
    ],
    extras_require={
        'test': [
            'pytest',
            'pytest-cov',
            'coveralls',
        ]
    }
)
