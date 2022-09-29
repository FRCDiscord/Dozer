"""News source to send a notification whenever a twitch streamer goes live."""

import datetime
import logging
from typing import TYPE_CHECKING

import discord
from dateutil import parser

from .AbstractSources import DataBasedSource

if TYPE_CHECKING:
    from dozer import Dozer
DOZER_LOGGER = logging.getLogger('dozer')


class TwitchSource(DataBasedSource):
    """News source to send a notification whenever a twitch streamer goes live."""
    full_name: str = "Twitch"
    short_name: str = "twitch"
    base_url: str = "https://twitch.tv"
    description: str = "Makes a post whenever a specified user goes live on Twitch"

    token_url: str = "https://id.twitch.tv/oauth2/token"
    api_url: str = "https://api.twitch.tv/helix"
    color: discord.Colour = discord.Color.from_rgb(145, 70, 255)

    class TwitchUser(DataBasedSource.DataPoint):
        """A helper class to represent a single Twitch streamer"""

        def __init__(self, user_id, display_name, profile_image_url, login):
            super().__init__(login, display_name)
            self.user_id = user_id
            self.display_name = display_name
            self.profile_image_url = profile_image_url
            self.login = login

    def __init__(self, aiohttp_session, bot: "Dozer"):
        super().__init__(aiohttp_session, bot)
        self.access_token = None
        self.client_id = None
        self.expiry_time = None
        self.users = {}
        self.seen_streams = set()

    async def get_token(self):
        """Use OAuth2 to request a new token. If token fails, disable the source."""
        client_id = self.bot.config['news']['twitch']['client_id']
        self.client_id = client_id
        client_secret = self.bot.config['news']['twitch']['client_secret']
        params = {
            'client_id': client_id,
            'client_secret': client_secret,
            'grant_type': 'client_credentials'
        }
        response = await self.http_session.post(self.token_url, params=params)
        response = await response.json()
        try:
            self.access_token = response['access_token']
        except KeyError:
            DOZER_LOGGER.critical(f"Error in {self.full_name} Token Get: {response['message']}")
            self.disabled = True
            return

        expiry_seconds = response['expires_in']
        time_delta = datetime.timedelta(seconds=expiry_seconds)
        self.expiry_time = datetime.datetime.now() + time_delta

    async def request(self, url, *args, headers=None, **kwargs):
        """Make a OAuth2 verified request to a API Endpoint"""
        if headers is None:
            headers = {'Authorization': f"Bearer {self.access_token}",
                       "Client-ID": self.client_id}
        else:
            headers['Authorization'] = f"Bearer {self.access_token}"

        url = f"{self.api_url}/{url}"

        response = await self.http_session.get(url, headers=headers, *args, **kwargs)

        if response.status == 401:
            if 'WWW-Authenticate' in response.headers:
                DOZER_LOGGER.info("Twitch token expired when request made, request new token and retrying.")
                await self.get_token()
                return await self.request(url, headers=headers, *args, **kwargs)

        json = await response.json()
        return json

    async def first_run(self, data=None):
        """Make sure we have a token, then verify and add all the current users in the DB"""
        await self.get_token()

        if not data:
            return

        params = []
        for login in data:
            params.append(('login', login))
        json = await self.request("users", params=params)
        for user in json['data']:
            user_obj = TwitchSource.TwitchUser(user['id'], user['display_name'], user['profile_image_url'],
                                               user['login'])
            self.users[user['id']] = user_obj

    async def clean_data(self, text):
        """Request user data from Twitch to verify the username exists and clean the data"""
        try:
            user_obj = self.users[text]
        except KeyError:
            json = await self.request('users', params={'login': text})
            if len(json['data']) == 0:
                raise DataBasedSource.InvalidDataException("No user with that login name found")
            elif len(json['data']) > 1:
                raise DataBasedSource.InvalidDataException("More than one user with that login name found")

            user_obj = TwitchSource.TwitchUser(json['data'][0]['id'], json['data'][0]['display_name'],
                                               json['data'][0]['profile_image_url'], json['data'][0]['login'])

        return user_obj

    async def add_data(self, obj):
        """Add the user object to the store"""
        self.users[obj.user_id] = obj
        return True

    async def remove_data(self, obj):
        """Remove the user object from the store"""
        try:
            del self.users[obj.user_id]
            return True
        except KeyError:
            return False

    async def get_new_posts(self):
        """Assemble all the current user IDs, get any game names and return the embeds and strings"""
        if datetime.datetime.now() > self.expiry_time:
            DOZER_LOGGER.info("Refreshing Twitch token due to expiry time")
            await self.get_token()

        params = []
        for user in self.users.values():
            params.append(('user_id', user.user_id))
        params.append(('first', len(self.users)))
        json = await self.request("streams", params=params)

        if len(json['data']) == 0:
            return {}

        # streams endpoint only returns game ID, do a second request to get game names
        game_ids = []
        for stream in json['data']:
            game_ids.append(stream['game_id'])

        params = []
        for game in game_ids:
            params.append(('id', game))
        games_json = await self.request("games", params=params)
        games = {}
        for game in games_json['data']:
            games[game['id']] = game['name']

        posts = {}
        for stream in json['data']:
            if stream['id'] not in self.seen_streams:
                embed = self.generate_embed(stream, games)
                plain = self.generate_plain_text(stream, games)
                posts[stream['user_name']] = {
                    'embed': [embed],
                    'plain': [plain]
                }

                self.seen_streams.add(stream['id'])

        return posts

    def generate_embed(self, data, games):
        """Given data on a stream and a dict of games, assemble an embed"""
        try:
            display_name = data['display_name']
        except KeyError:
            display_name = data['user_name']

        embed = discord.Embed()
        embed.title = f"{display_name} is now live on Twitch!"
        embed.colour = self.color

        embed.description = data['title']

        embed.url = f"https://www.twitch.tv/{data['user_name']}"

        embed.add_field(name="Playing", value=games[data['game_id']], inline=True)
        embed.add_field(name="Watching", value=data['viewer_count'], inline=True)

        embed.set_author(name=display_name, url=embed.url, icon_url=self.users[data['user_id']].profile_image_url)

        embed.set_image(url=data['thumbnail_url'].format(width=1920, height=1080))

        start_time = parser.isoparse(data['started_at'])
        embed.timestamp = start_time

        return embed

    @staticmethod
    def generate_plain_text(data, games):
        """Given data on a stream and a dict of games, assemble a string"""
        try:
            display_name = data['display_name']
        except KeyError:
            display_name = data['user_name']

        return f"{display_name} is now live on Twitch!\n" \
               f"Playing {games[data['game_id']]} with  {data['viewer_count']} currently watching\n" \
               f"Watch at https://www.twitch.tv/{data['user_name']}"
