from dateutil import parser
import discord
import datetime
import logging

from .AbstractSources import DataBasedSource

DOZER_LOGGER = logging.getLogger('dozer')


class TwitchSource(DataBasedSource):
    full_name = "Twitch"
    short_name = "twitch"
    base_url = "https://twitch.tv"
    description = "Makes a post whenever a specified user goes live on Twitch"

    token_url = "https://id.twitch.tv/oauth2/token"
    api_url = "https://api.twitch.tv/helix"
    color = discord.Color.from_rgb(145, 70, 255)

    class TwitchUser(DataBasedSource.DataPoint):
        def __init__(self, user_id, display_name, profile_image_url, login):
            super().__init__(login, display_name)
            self.user_id = user_id
            self.display_name = display_name
            self.profile_image_url = profile_image_url
            self.login = login

    def __init__(self, aiohttp_session, bot):
        super().__init__(aiohttp_session, bot)
        self.access_token = None
        self.client_id = None
        self.expiry_time = None
        self.users = {}
        self.seen_streams = set()

    async def get_token(self):
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

    async def request(self, url, headers=None, *args, **kwargs):
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
                return await self.request(url, headers, *args, **kwargs)

        json = await response.json()
        return json

    async def first_run(self, data=None):
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
        self.users[obj.user_id] = obj
        return True

    async def remove_data(self, obj):
        try:
            del self.users[obj.user_id]
            return True
        except KeyError:
            return False

    async def get_new_posts(self):
        if datetime.datetime.now() > self.expiry_time:
            DOZER_LOGGER.info(f"Refreshing Twitch token due to expiry time")
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

    def generate_plain_text(self, data, games):
        try:
            display_name = data['display_name']
        except KeyError:
            display_name = data['user_name']

        return f"{display_name} is now live on Twitch!\n" \
               f"Playing {games[data['game_id']]} with  {data['viewer_count']} currently watching\n" \
               f"Watch at https://www.twitch.tv/{data['user_name']}"