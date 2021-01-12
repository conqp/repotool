#! /usr/bin/env python3
"""Install script."""


from setuptools import setup


setup(
    name='repotool',
    use_scm_version=True,
    setup_requires=['setuptools_scm'],
    author='Richard Neumann',
    author_email='mail@richard-neumann.de',
    python_requires='>=3.8',
    py_modules=['repotool'],
    entry_points={'console_scripts': ['repotool = repotool:main']},
    url='https://github.com/conqp/repotool',
    license='GPLv3',
    description='Arch linux repositry management tool.',
    keywords='pacman mirror list mirrorlist optimizer filter'
)
