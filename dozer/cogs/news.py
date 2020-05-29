import logging
from asyncio import CancelledError, InvalidStateError
import aiohttp
import datetime
import traceback

import discord
from discord.ext import tasks
from discord.ext.commands import guild_only

from ._utils import *
from .. import db
from ..sources import *

DOZER_LOGGER = logging.getLogger('dozer')


def str_or_none(obj):
    if obj is None:
        return None
    else:
        return str(obj)


class News(Cog):
    enabled_sources = [FRCBlogPosts, CDLatest, TestSource, TwitchSource]
    kinds = ['plain', 'embed']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.updated = True
        self.sources = {}

    @Cog.listener('on_ready')
    async def startup(self):
        self.sources = {}
        for source in self.enabled_sources:
            self.sources[source.short_name] = source(aiohttp_session=aiohttp.ClientSession(), bot=self.bot)
            if issubclass(source, DataBasedSource):
                subs = await NewsSubscription.get_by(source=source.short_name)
                data = set()
                for sub in subs:
                    data.add(sub.data)
                await self.sources[source.short_name].first_run(data)
            else:
                await self.sources[source.short_name].first_run()
        self.get_new_posts.change_interval(minutes=self.bot.config['news']['check_interval'])
        self.get_new_posts.start()

    def cog_unload(self):
        self.get_new_posts.cancel()
        for source in self.sources:
            self.bot.loop.run_until_complete(source.http_session.close())

    @tasks.loop()
    async def get_new_posts(self):
        DOZER_LOGGER.debug('Getting new news posts.')
        for source in self.sources.values():
            DOZER_LOGGER.debug(f"Getting source {source.full_name}")
            subs = await NewsSubscription.get_by(source=source.short_name)
            if not subs:
                DOZER_LOGGER.debug(f"Skipping source {source.full_name} due to no subscriptions")
                continue

            channel_dict = {}
            # of the form
            # {
            #   'data_name': {
            #       discord.Channel: 'plain' or 'embed'
            #   },
            #   'other_data': {
            #       discord.Channel: 'plain' or 'embed',
            #       discord.Channel: 'plain' or 'embed'
            #   }
            # }
            for sub in subs:
                channel = self.bot.get_channel(sub.channel_id)
                if channel is None:
                    DOZER_LOGGER.error(f"Channel {sub.channel_id} (sub ID {sub.id}) returned None. Removing sub "
                                       f"from Sub list.")
                    await NewsSubscription.delete(id=sub.id)
                    continue

                if sub.data is None:
                    sub.data = 'source'

                if sub.data not in channel_dict.keys():
                    channel_dict[sub.data] = {}

                channel_dict[sub.data][channel] = sub.kind

            posts = await source.get_new_posts()
            if posts is None:
                if source.disabled:
                    del self.sources[source.short_name]
                continue

            for (data, channels) in channel_dict.items():
                for (channel, kind) in channels.items():
                    try:
                        if kind == 'embed':
                            for embed in posts[data]['embed']:
                                await channel.send(embed=embed)
                        elif kind == 'plain':
                            for post in posts[data]['plain']:
                                await channel.send(post)
                    except KeyError:
                        # posts[data] did not exist, therefore no new posts for that data source
                        continue

        next_run = self.get_new_posts.next_iteration
        DOZER_LOGGER.debug(f"Done with getting news. Next run in "
                           f"{(next_run - datetime.datetime.now(datetime.timezone.utc)).total_seconds()}"
                           f" seconds.")

    # Whenever version 1.4.0 of discord.py comes out, this can be uncommented. For now, use the get_exception commmand
    # @get_new_posts.error()
    # async def log_exception(self, exception):
    #     DOZER_LOGGER.error(exception)

    @group(invoke_without_command=True)
    @guild_only()
    async def news(self, ctx):
        """Manage news subscriptions for the current server"""
        await ctx.send("todo")

    def get_source(self, name):
        chosen_source = None
        for enabled_source in self.sources.values():
            if name in enabled_source.aliases:
                chosen_source = enabled_source
                break
        return chosen_source

    @news.command()
    @guild_only()
    async def add(self, ctx, channel: discord.TextChannel,  source, kind='embed', data=None):
        """Add a new subscription of a given source to a channel."""

        chosen_source = self.get_source(source)

        if chosen_source is None:
            await ctx.send(f"No source under the name `{source}` found.")
            return

        if data is not None and not isinstance(chosen_source, DataBasedSource):
            await ctx.send(f"The source {source} does not accept extra data.")
            return

        if data is None and isinstance(chosen_source, DataBasedSource):
            await ctx.send(f"The source {chosen_source.full_name} needs data.")
            # TODO: add default source(s) to subscribe if given no data
            return

        if channel is None:
            await ctx.send(f"Cannot find the channel {channel}.")
            return

        if not channel.permissions_for(ctx.me).send_messages:
            await ctx.send(f"I don't have permission to post in f{channel.mention}.")
            return

        if channel.guild != ctx.guild:
            await ctx.send(f"The channel {channel.mention} does not belong to this server.")
            return

        if kind not in self.kinds:
            await ctx.send(f"{kind} is not a accepted kind of post. Accepted kinds are {', '.join(self.kinds)}")
            return

        data_obj = None
        if isinstance(chosen_source, DataBasedSource):
            try:
                data_obj = await chosen_source.clean_data(data)
            except DataBasedSource.InvalidDataException as e:
                await ctx.send(f"Data {data} is invalid. {e.args[0]}")
                return

            search_exists = await NewsSubscription.get_by(channel_id=channel.id, source=chosen_source.short_name,
                                                          data=str(data_obj))

            if search_exists:
                await ctx.send(f"There is already a subscription of {chosen_source.full_name} with data {data} "
                               f"in {channel.mention}")
                return

            await chosen_source.add_data(data_obj)
            # TODO: Check if source is already added before adding
        else:
            search_exists = await NewsSubscription.get_by(channel_id=channel.id, source=chosen_source.short_name)

            if search_exists:
                if search_exists[0].kind == kind:
                    await ctx.send(f"There is already a subscription of {chosen_source.full_name} for {channel.mention}.")
                    return
                else:
                    await ctx.send(f"There is already a subscription of {chosen_source.full_name} for {channel.mention}, "
                                   f"but with a different kind of post. To change the kind of posts, remove the "
                                   f"subscription first using `{self.bot.config['prefix']}news remove {channel.mention} "
                                   f"{chosen_source.short_name}` and add the subscription again with this command.")

        new_sub = NewsSubscription(channel_id=channel.id, guild_id=channel.guild.id, source=chosen_source.short_name,
                                   kind=kind, data=str_or_none(data_obj))
        await new_sub.update_or_add()

        embed = discord.Embed(title=f"Channel #{channel.name} subscribed to {chosen_source.full_name}",
                              description="New posts should be in this channel soon.")
        embed.add_field(name="Kind", value=kind)
        if isinstance(chosen_source, DataBasedSource):
            embed.add_field(name="Data", value=data_obj.full_name)

        embed.colour = discord.colour.Color.green()

        await ctx.send(embed=embed)

    @news.command()
    async def remove(self, ctx, channel: discord.TextChannel, source, data=None):
        chosen_source = self.get_source(source)

        if chosen_source is None:
            await ctx.send(f"The source `{source}` cannot be found.")

        if channel is None:
            await ctx.send(f"The channel {channel} cannot be found.")

        if channel.guild != ctx.guild:
            await ctx.send(f"The channel {channel.mention} does not belong to this server.")
            return

        if isinstance(chosen_source, DataBasedSource):
            try:
                data_obj = chosen_source.clean_data(data)
            except DataBasedSource.InvalidDataException as e:
                await ctx.send(f"Data {data} is invalid. {e.args[0]}")
                return

            sub = await NewsSubscription.get_by(channel_id=channel.id, guild_id=channel.guild.id,
                                                source=chosen_source.short_name, data=str(data_obj))
            if len(sub) == 0:
                await ctx.send(f"No subscription of {chosen_source.full_name} for channel {channel.mention} with data"
                               f"{data} found.")
            elif len(sub) > 1:
                DOZER_LOGGER.error(f"More that one subscription of {chosen_source.full_name} for channel "
                                   f"{channel.mention} with data {data} found when attempting to delete.")
                await ctx.send(f"More that one subscription of {chosen_source.full_name} for channel {channel.mention} "
                               f"with data {data} found. Please contact the Dozer administrator for help.")
                return

            # TODO: Check if any other subscriptions use this data first
            await chosen_source.remove_data(data_obj)
        else:
            sub = await NewsSubscription.get_by(channel_id=channel.id, guild_id=channel.guild.id,
                                                source=chosen_source.short_name)
            if len(sub) == 0:
                await ctx.send(f"No subscription of {chosen_source.full_name} for channel {channel.mention} found.")
                return

            elif len(sub) > 1:
                if isinstance(chosen_source, DataBasedSource):
                    await ctx.send("There ware multiple subscriptions found. Try again with a data parameter.")
                    return
                else:
                    DOZER_LOGGER.error(f"More than one subscription of {chosen_source.full_name} for channel "
                                       f"{channel.mention} found when attempting to delete.")
                    await ctx.send(f"More than one subscription of {chosen_source.full_name} for channel "
                                   f"{channel.mention} was found. Please contact the Dozer administrators for help.")
                    return

        await NewsSubscription.delete(id=sub[0].id)

        embed = discord.Embed(title=f"Subscription of channel #{channel.name} to {chosen_source.full_name} removed",
                              description="Posts from this source will no longer appear.")
        if isinstance(chosen_source, DataBasedSource):
            embed.add_field(name="Data", value=sub[0].data)

        embed.colour = discord.colour.Color.red()

        await ctx.send(embed=embed)

    @news.command(name='sources')
    async def list_sources(self, ctx):
        embed = discord.Embed(title="All available sources to subscribe to.")

        embed.description = f"To subscribe to any of these sources, use the `{self.bot.command_prefix}news add " \
                            f"<channel> <source name.` command."

        for source in self.sources.values():
            aliases = ", ".join(source.aliases)
            embed.add_field(name=f"{source.full_name}",
                            value=f"[{source.description}]({source.base_url})\n\nPossible Names: `{aliases}`",
                            inline=True)

        await ctx.send(embed=embed)

    @news.command(name='subscriptions', aliases=('subs', 'channels'))
    async def list_subscriptions(self, ctx, channel: discord.TextChannel = None):
        if channel is not None:
            results = await NewsSubscription.get_by(guild_id=ctx.guild.id, channel_id=ctx.channel.id)
        else:
            results = await NewsSubscription.get_by(guild_id=ctx.guild.id)

        if not results:
            embed = discord.Embed(title="News Subscriptions for {}".format(ctx.guild.name))
            embed.description = f"No news subscriptions found for this guild! Add one using `{self.bot.command_prefix}"\
                                f"news add <channel> <source>`"
            embed.colour = discord.Color.red()
            await ctx.send(embed=embed)
            return

        channels = {}
        for result in results:
            channel = ctx.bot.get_channel(result.channel_id)
            if channel is None:
                DOZER_LOGGER.error(f"Channel ID {result.channel_id} for subscription ID {result.id} not found. This "
                                   f"subscription will be removed on the next run of subscriptions.")
                continue

            try:
                channels[channel].append(result)
            except KeyError:
                channels[channel] = [result]

        embed = discord.Embed()
        embed.title = "News Subscriptions for {}".format(ctx.guild.name)
        embed.colour = discord.Color.dark_orange()
        for channel, lst in channels.items():
            subs = ""
            for sub in lst:
                subs += f"{sub.source}"
                if sub.data:
                    subs += f": {sub.data}"
                subs += "\n"
            embed.add_field(name=f"#{channel.name}", value=subs)
        await ctx.send(embed=embed)

    @news.command()
    @dev_check()
    async def restart_loop(self, ctx):
        self.get_new_posts.stop()
        self.get_new_posts.change_interval(minutes=self.bot.config['news']['check_interval'])
        self.get_new_posts.start()
        await ctx.send("Loop restarted.")

    @news.command()
    @dev_check()
    async def next_run(self, ctx):
        next_run = self.get_new_posts.next_iteration
        if next_run is None:
            await ctx.send(f"No next run scheduled. This likely means an exception occurred in the loop. Check this "
                           f"exception using {self.bot.config.prefix}news get_exception, and then restart using "
                           f"{self.bot.config.prefix}news restart_loop if appropriate. ")
        else:
            await ctx.send(f"Next run in "
                           f"{(next_run - datetime.datetime.now(datetime.timezone.utc)).total_seconds()} seconds.")

    @news.command()
    @dev_check()
    async def get_exception(self, ctx):
        try:
            exception = self.get_new_posts.get_task().exception()
            if exception is None:
                await ctx.send("No exception occurred.")
            else:
                tb_str = traceback.format_exception(etype=type(exception), value=exception, tb=exception.__traceback__)
                await ctx.send(f"```{''.join(tb_str)}```")
        except CancelledError:
            await ctx.send("Task has been cancelled.")
        except InvalidStateError:
            await ctx.send("Task has not yet completed. This likely means the loop is continuing just fine. You can"
                           f"determine the next time it's running with {self.bot.config.prefix}news next_run")


def setup(bot):
    """Setup cog"""

    bot.add_cog(News(bot))


class NewsSubscription(db.DatabaseTable):
    """Represents a single subscription of one news source to one channel"""
    __tablename__ = 'news_subs'
    __uniques__ = 'id'

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
            kind varchar NOT NULL
            )""")

    def __init__(self, channel_id, guild_id, source, kind, data=None, id=None):
        super().__init__()
        self.id = id
        self.channel_id = channel_id
        self.guild_id = guild_id
        self.source = source
        self.kind = kind
        self.data = data

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = NewsSubscription(id=result.get("id"), channel_id=result.get("channel_id"),
                                   guild_id=result.get("guild_id"), source=result.get("source"),
                                   kind=result.get("kind"), data=result.get("data"))
            result_list.append(obj)
        return result_list
