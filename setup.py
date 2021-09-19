#!/usr/bin/env python3

from distutils.core import setup

setup(
        name='redp', 
        version='0.1', 
        description='Converts reddit submissions and comments to a maildir', 
        author='Peter J. Schroeder', 
        author_email='peterjschroeder@gmail.com', 
        url='https://github.com/peterjschroeder/redp',
        scripts=['redpick', 'redpull', 'redpush'],
        install_requires=['archivenow', 'asciimatics', 'better-profanity', 'configparser', 'gallery-dl @ git+https://github.com/mikf/gallery-dl.git', 'natsort', 'praw', 'pmaw', 'python-pidfile', 'pyxdg', 'tqdm', 'youtube-dl']
)

