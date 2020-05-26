"""Provide helper classes and end classes for source data"""

import aiohttp
import xml.etree.ElementTree
import discord
import datetime


class Source:
    """Abstract base class for a data source."""

    source_name = "Source Name"
    short_name = "src"
    accepts_data = False

    def __init__(self, aiohttp_session: aiohttp.ClientSession):
        self.http_session = aiohttp_session

    async def get_new_posts(self):
        """Fetches latest data from an arbitrary source. This should return an dict with two lists in it. The dict
        should be of the following format:
        new_posts = {
            'embed': [discord.Embed, discord.Embed.....],
            'plain': [str, str, ...]
        }
        The two lists do not need to be in the same order.
        """
        return NotImplementedError

    async def first_run(self):
        """Function to be run first time around. This can be used for example to fetch current posts in the RSS
        feed to not show on boot. If this is not needed, simple leave as is. """
        return


class RSSSource(Source):
    url = None
    color = discord.colour.Color.blurple()
    date_format = "%a, %d %b %Y %H:%M:%S %z"  # format for datetime.strptime()

    def __init__(self, aiohttp_session: aiohttp.ClientSession):
        super().__init__(aiohttp_session)
        self.guids_seen = set()

    async def first_run(self):
        response = await self.fetch()
        self.parse(response, True)
        print(self.guids_seen)

    async def get_new_posts(self):
        response = await self.fetch()
        items = self.parse(response)
        new_posts = {
            'embed': [],
            'plain': []
        }
        for item in items:
            data = self.get_data(item)
            new_posts['embed'] += self.generate_embed(data)
            new_posts['plain'] += self.generate_plain_text(data)
        return new_posts

    async def fetch(self):
        response = await self.http_session.get(url=self.url)
        return await response.text()

    def parse(self, response, first_time=False):
        new_items = set()
        root = xml.etree.ElementTree.fromstring(response)
        channel = root[0]
        for child in channel:
            if child.tag == 'item':
                guid = child.find('guid')
                if first_time:
                    self.guids_seen.add(guid.text)
                    continue
                new = self.determine_if_new(guid.text)
                if new:
                    new_items.add(child)
        return new_items

    def determine_if_new(self, guid):
        """Given a RSS item's guid, determine if this item is new or not. Store GUID if new."""
        if guid not in self.guids_seen:
            self.guids_seen.add(guid)
            return True
        else:
            return False

    def get_data(self, item):
        data = {'title': item.find('title').text, 'url': item.find('url').text,
                'author': item.find("{http://purl.org/dc/elements/1.1/}creator").text}
        date_string = item.find('pubDate')
        data['date'] = datetime.datetime.strptime(date_string, self.date_format)
        return dict

    def generate_embed(self, data):
        embed = discord.Embed()
        embed.title = f"New Post From {self.source_name}!"
        embed.color = self.color
        embed.description = f"[{data['title']}]({data['url']})"

        embed.set_author(name=data['author'])

        embed.timestamp = data['date']

        return embed

    def generate_plain_text(self, data):
        return f"New Post from {self.source_name} from {data['author']}: [{data['title']}]({data['url']})"


class FRCBlogPosts(RSSSource):
    url = "https://www.firstinspires.org/robotics/frc/blog-rss"
    source_name = "FRC Blog Posts"
    short_name = "frc"
    color = discord.colour.Color.dark_blue()


class CDLatest(RSSSource):
    url = "https://www.chiefdelphi.com/latest.rss"
    source_name = "Chief Delphi"
    short_name = "cd"
    color = discord.colour.Color.orange()
