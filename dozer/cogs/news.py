import asyncio

import discord
from discord.ext.commands import guild_only
from discord.ext import tasks

from ._utils import *
from .. import db
from ..sources import *


class News(Cog):
    enabled_sources = [FRCBlogPosts, CDLatest]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sources = {}

    @Cog.listener('on_ready')
    async def startup(self):
        for source in self.enabled_sources:
            self.sources[source.short_name] = source(aiohttp_session=aiohttp.ClientSession())
            await self.sources[source.short_name].first_run()

    @group()
    @guild_only()
    async def news(self, ctx):
        """Manage news subscriptions for the current server"""
        results = await NewsSubscription.get_by(guild_id=ctx.guild.id)

        if not results:
            embed = discord.Embed(title="News Subscriptions for {}".format(ctx.guild.name))
            embed.description = "No news subscriptions found for this guild! Add one using `{}news add <source>`".format(
                ctx.bot.command_prefix)
            embed.color = discord.Color.red()
            await ctx.send(embed=embed)
            return

        fmt = "{bot.get_channel(0.channel_id).name}: {source}"
        news_text = '\n'.join(map(fmt.format, results))

        embed = discord.Embed()
        embed.title = "News Subscriptions for {}".format(ctx.guild.name)
        embed.add_field(name="Filters", value=news_text)
        embed.color = discord.Color.dark_orange()
        await ctx.send(embed=embed)


def setup(bot):
    """Setup cog"""

    bot.add_cog(News(bot))


class NewsSubscription(db.DatabaseTable):
    """Represents a single subscription of one news source to one channel"""
    __tablename__ = 'news_subs'
    __uniques__ = 'is'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            id serial PRIMARY KEY NOT NULL,
            channel_id bigint NOT NULL,
            guild_id bigint NOT NULL,
            source varchar NOT NULL,
            data varchar,
            plaintext boolean default false NOT NULL
            )""")

    def __init__(self, id, channel_id, guild_id, source, data=None):
        super().__init__()
        self.id = id
        self.channel_id = channel_id
        self.guild_id = guild_id
        self.source = source
        self.data = data

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = NewsSubscription(id=result.get("id"), channel_id=result.get("channel_id"),
                                   guild_id=result.get("guild_id"), source=result.get("source"),
                                   data=result.get("data"))
            result_list.append(obj)
        return result_list
