"""A collection of sources for various FIRST-related news sources"""

from .AbstractSources import Source, DataBasedSource
from .RSSSources import *
from .RedditSource import RedditSource
from .TwitchSource import TwitchSource

sources = [TwitchSource, RedditSource]
sources += [source for source in RSSSource.__subclasses__() if not source.disabled]
