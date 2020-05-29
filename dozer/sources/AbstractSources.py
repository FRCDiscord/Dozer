"""Provide helper classes and end classes for source data"""
import aiohttp

from dateutil import parser
import discord
import datetime
import logging

DOZER_LOGGER = logging.getLogger('dozer')


class Source:
    """Abstract base class for a data source."""

    full_name = "Source Name"
    short_name = "src"
    base_url = None
    aliases = tuple()
    description = "Description"
    disabled = False

    def __init__(self, aiohttp_session: aiohttp.ClientSession, bot):
        self.aliases += (self.full_name, self.short_name)
        self.http_session = aiohttp_session
        self.bot = bot

    async def get_new_posts(self):
        """Fetches latest data from an arbitrary source. This should return an dict with two lists in it. The dict
        should be of the following format:
        new_posts = {
            'source': {
                'embed': [discord.Embed, discord.Embed, ...],
                'plain': [str, str, ...]
            }
        }
        The two lists inside each source do not need to be in the same order. If you are defining a source with multiple
        data points (say, multiple twitch or youtube channels), each data point should be the name of the first order
        dict ('source') in the above example. If the source only has one data point, name it 'source' as seen above.
        """
        return NotImplementedError

    async def first_run(self):
        """Function to be run first time around. This can be used for example to fetch current posts in the RSS
        feed to not show on boot or to validate tokens. If this is not needed, simply leave as is. """
        return


class DataBasedSource(Source):

    def __init__(self, aiohttp_session: aiohttp.ClientSession, bot):
        super().__init__(aiohttp_session, bot)

    async def clean_data(self, text):
        """Takes a user-inputted string and should return a DataPoint object that can be stored in the database.
        If the data is invalid, this function should raise a InvalidDataException with a specific reason as the
        exception attribute. This reason will be displayed to the user."""
        return text

    async def add_data(self, obj):
        """Takes a object that's been run through clean_data and should perform any processing that the bot needs to
        store current data sources. This function is run when &news add is run, but is not automatically run on bot
        startup. Any data that needs to be initialized during the bot's first run should be put in first_run.

        You can assume this function is only ran when this data source has not already been added once before.

        This function should return True is the data was successfully added, and False if the data was not."""
        raise NotImplementedError

    async def remove_data(self, obj):
        """This function is run when &news remove is run and the currently initialized source needs to stop fetching
        and returning that specific data point. You can assume obj has been run through clean_data.

        You can assume this function is ran when the &news remove has removed all instances of that data point. Once
        this function is called, you can assume you will not need to get that data source again unless add_data is run
        again.

        This function should return True is the data was successfully removed, and False if the data was not."""
        raise NotImplementedError

    async def first_run(self, data=None):
        return

    class InvalidDataException(Exception):
        def __init__(self, *attr):
            super().__init__(*attr)

    class DataPoint:
        """A helper object that should be returned by clean_data.
            short_name: The string that will be stored in the database (by default). If you'd like to change this
        behaviour, change the implementation of __str__ in your subclass.
            full_name: The string that will be displayed to the user of your cleaned, verified data.
        """
        def __init__(self, short_name, full_name):
            self.short_name = short_name
            self.full_name = full_name

        def __str__(self):
            return self.short_name