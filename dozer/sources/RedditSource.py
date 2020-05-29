from .AbstractSources import DataBasedSource
import discord


class RedditSource(DataBasedSource):
    full_name = "Reddit"
    short_name = "reddit"
    base_url = "https://twitch.tv"
    description = "Gets latest posts from any given "

    token_url = "https://www.reddit.com/api/v1/access_token"
    api_url = "https://api.twitch.tv/helix"
    color = discord.Color.from_rgb(145, 70, 255)