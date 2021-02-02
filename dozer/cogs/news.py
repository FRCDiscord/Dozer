"""Commands and management for news subscriptions"""

import logging
from asyncio import CancelledError, InvalidStateError
import datetime
import traceback
import xml.etree.ElementTree as ElementTree
import aiohttp

import discord
from discord.ext import tasks
from discord.ext.commands import guild_only, has_permissions, BadArgument

from ._utils import *
from .. import db
from ..sources import DataBasedSource, Source, sources

DOZER_LOGGER = logging.getLogger('dozer')


def str_or_none(obj):
    """A helper function to make sure str(None) returns None instead of 'None' """
    if obj is None:
        return None
    else:
        return str(obj)


class News(Cog):
    """Commands and management for news subscriptions"""
    enabled_sources = sources
    kinds = ['plain', 'embed']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.updated = True
        self.http_source = None
        self.sources = {}
        self.get_new_posts.change_interval(minutes=self.bot.config['news']['check_interval'])
        self.get_new_posts.start()

    def cog_unload(self):
        """Attempt to gracefully shut down the loop. Doesn't generally work. """
        self.get_new_posts.cancel()

    @tasks.loop()
    async def get_new_posts(self):
        """Attempt to get current subscriptions and post new posts in the respective channels"""
        DOZER_LOGGER.debug('Getting new news posts.')
        to_delete = [source.short_name for source in self.sources.values() if source.disabled]
        for name in to_delete:
            del self.sources[name]

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
                    DOZER_LOGGER.error(f"Channel {sub.channel_id} (sub ID {sub.id}) returned None. Not removing this"
                                       f"in case it's a discord error, but if discord is fine it's recommended to "
                                       f"remove this channel manually.")
                    continue

                if sub.data is None:
                    sub.data = 'source'

                if sub.data not in channel_dict.keys():
                    channel_dict[sub.data] = {}

                channel_dict[sub.data][channel] = sub.kind

            # We've gotten all of the channels we need to post to, lets get the posts and post them now
            try:
                posts = await source.get_new_posts()
            except ElementTree.ParseError:
                DOZER_LOGGER.error(f"XML Parser errored out on source f{source.full_name}")
                continue
            if posts is None:
                continue

            for (data, channels) in channel_dict.items():
                for (channel, kind) in channels.items():
                    if data not in posts:
                        continue
                    if kind == 'embed':
                        for embed in posts[data]['embed']:
                            await channel.send(embed=embed)
                    elif kind == 'plain':
                        for post in posts[data]['plain']:
                            await channel.send(post)

        next_run = self.get_new_posts.next_iteration
        DOZER_LOGGER.debug(f"Done with getting news. Next run in "
                           f"{(next_run - datetime.datetime.now(datetime.timezone.utc)).total_seconds()}"
                           f" seconds.")

    @get_new_posts.error
    async def log_exception(self, _exception):
        """Catch error in the news loop and attempt to restart"""
        DOZER_LOGGER.error(f"News fetch encountered an error: \"{_exception}\", attempting to restart")
        self.get_new_posts.restart()
        DOZER_LOGGER.debug("News fetch successfully restarted")

    @get_new_posts.before_loop
    async def startup(self):
        """Initialize sources and start the loop after initialization"""
        self.sources = {}
        if self.http_source:
            await self.http_source.close()
        self.http_source = aiohttp.ClientSession(headers={'Connection': 'keep-alive', 'User-Agent': 'Dozer RSS Feed Reader'})
        # JVN's blog will 403 you if you use the default user agent, so replacing it with this will yield a parsable result.
        for source in self.enabled_sources:
            try:
                self.sources[source.short_name] = source(aiohttp_session=self.http_source, bot=self.bot)
                if issubclass(source, DataBasedSource):
                    subs = await NewsSubscription.get_by(source=source.short_name)
                    data = {sub.data for sub in subs}
                    await self.sources[source.short_name].first_run(data)
                else:
                    await self.sources[source.short_name].first_run()
            except ElementTree.ParseError as err:
                del self.sources[source.short_name]
                DOZER_LOGGER.error(f"Parsing error in source {source.short_name}: {err}")

    @Cog.listener()
    async def on_guild_channel_delete(self, channel):
        """Called when a channel is deleted, so it can be removed from the newsfeed"""
        await NewsSubscription.delete(channel_id=channel.id)

    @group(invoke_without_command=True)
    @guild_only()
    async def news(self, ctx):
        """Show help for news subscriptions"""
        embed = discord.Embed(title="How to subscribe to News Sources",
                              description="Dozer has built in news scrapers to allow you to review up to date news"
                                          "in specific channels. See below on how to manage your server's "
                                          "subscriptions")
        embed.add_field(name="How to add a subscription",
                        value=f"To add a source, for example, Chief Delphi to a channel, you can use the command"
                              f"`{ctx.bot.command_prefix}news add #channel cd`")
        embed.add_field(name="Plain text posts",
                        value=f"To use plain text posts instead of embeds, you can use a command like"
                              f"`{ctx.bot.command_prefix}news add #channel cd plain`")
        embed.add_field(name="Data based sources",
                        value=f"Some sources accept data, like Reddit. To add a reddit subreddit, for example the FRC "
                              f"subreddit you can use the command `{ctx.prefix}news add #channel reddit "
                              f"embed frc`")
        embed.add_field(name="Removing Subscriptions",
                        value=f"To remove a source, like Chief Delphi, use `{ctx.prefix}news remove #channel cd`")
        embed.add_field(name="List all sources",
                        value=f"To see all sources, use `{ctx.prefix}news sources`")
        embed.add_field(name="List all subscriptions",
                        value=f"To see all of your server's subscriptions, use `{ctx.prefix}news "
                              f"subscriptions`")
        await ctx.send(embed=embed)

    news.example_usage = "`{prefix}news` - Get a small guide on using the News system"

    @news.command()
    @has_permissions(manage_guild=True)
    @guild_only()
    async def add(self, ctx, channel: discord.TextChannel, source: Source, kind='embed', data=None):
        """Add a new subscription of a given source to a channel."""

        if data is None and kind not in self.kinds and isinstance(source, DataBasedSource):
            data = kind
            kind = 'embed'

        if data is not None and not isinstance(source, DataBasedSource):
            raise BadArgument(f"The source {source.full_name} does not accept extra data.")

        if data is None and isinstance(source, DataBasedSource):
            raise BadArgument(f"The source {source.full_name} needs data. To subscribe with data, try "
                              f"`{ctx.prefix}news add {source.short_name} {channel.mention} embed data`")

        if not channel.permissions_for(ctx.me).send_messages:
            raise BadArgument(f"I don't have permission to post in {channel.mention}.")

        if channel.guild != ctx.guild:
            raise BadArgument(f"The channel {channel.mention} does not belong to this server.")

        if kind not in self.kinds:
            raise BadArgument(f"{kind} is not a accepted kind of post. Accepted kinds are {', '.join(self.kinds)}")

        data_obj = None
        if isinstance(source, DataBasedSource):
            try:
                data_obj = await source.clean_data(data)
            except DataBasedSource.InvalidDataException as e:
                raise BadArgument(f"Data {data} is invalid. {e.args[0]}")

            search_exists = await NewsSubscription.get_by(channel_id=channel.id, source=source.short_name,
                                                          data=str(data_obj))

            if search_exists:
                raise BadArgument(f"There is already a subscription of {source.full_name} with data {data} "
                                  f"in {channel.mention}")

            added = await source.add_data(data_obj)
            if not added:
                DOZER_LOGGER.error(f"Failed to add data {data_obj} to source {source.full_name}")
                await ctx.send("Failed to add new data source. Please contact the Dozer Administrators.")
                return

            data_exists = await NewsSubscription.get_by(source=source.short_name, data=str(data_obj))
            if not data_exists:
                await source.add_data(data_obj)
        else:
            search_exists = await NewsSubscription.get_by(channel_id=channel.id, source=source.short_name)

            if search_exists:
                if search_exists[0].kind == kind:
                    raise BadArgument(f"There is already a subscription of {source.full_name} for {channel.mention}.")
                else:
                    await ctx.send(f"There is already a subscription of {source.full_name} for {channel.mention}, "
                                   f"but with a different kind of post. To change the kind of posts, remove the "
                                   f"subscription first using `{ctx.prefix}news remove {channel.mention}"
                                   f" {source.short_name}` and add the subscription again with this command.")
                    return

        new_sub = NewsSubscription(channel_id=channel.id, guild_id=channel.guild.id, source=source.short_name,
                                   kind=kind, data=str_or_none(data_obj))
        await new_sub.update_or_add()

        embed = discord.Embed(title=f"Channel #{channel.name} subscribed to {source.full_name}",
                              description="New posts should be in this channel soon.")
        embed.add_field(name="Kind", value=kind)
        if isinstance(source, DataBasedSource):
            embed.add_field(name="Data", value=data_obj.full_name)

        embed.colour = discord.colour.Color.green()

        await ctx.send(embed=embed)

    add.example_usage = """`{prefix}news add #news cd` - Make new Chief Delphi posts appear in #news
    `{prefix}news add #announcements frc plain` - Add new FRC blog posts in plain text to #announcements
    `{prefix}news add #reddit reddit embed frc` - Add new posts from /r/FRC to #reddit"""

    @news.command()
    @has_permissions(manage_guild=True)
    @guild_only()
    async def remove(self, ctx, channel: discord.TextChannel, source: Source, data=None):
        """Remove a subscription of a given source from a specific channel"""
        if isinstance(source, DataBasedSource):
            if data is None:
                raise BadArgument(f"The source {source.full_name} needs data.")

            try:
                data_obj = await source.clean_data(data)
            except DataBasedSource.InvalidDataException as e:
                await ctx.send(f"Data {data} is invalid. {e.args[0]}")
                return

            sub = await NewsSubscription.get_by(channel_id=channel.id, guild_id=channel.guild.id,
                                                source=source.short_name, data=str(data_obj))
            if len(sub) == 0:
                await ctx.send(f"No subscription of {source.full_name} for channel {channel.mention} with data "
                               f"{data_obj} found.")
                return
            elif len(sub) > 1:
                DOZER_LOGGER.error(f"More that one subscription of {source.full_name} for channel "
                                   f"{channel.mention} with data {data} found when attempting to delete.")
                await ctx.send(f"More that one subscription of {source.full_name} for channel {channel.mention} "
                               f"with data {data} found. Please contact the Dozer administrator for help.")
                return

            data_exists = await NewsSubscription.get_by(source=source.short_name, data=str(data_obj))
            if len(data_exists) > 1:
                removed = await source.remove_data(data_obj)
                if not removed:
                    DOZER_LOGGER.error(f"Failed to remove data {data_obj} from source {source.full_name}")
                    await ctx.send("Failed to remove data source. Please contact the Dozer Administrators.")
                    return

        else:
            sub = await NewsSubscription.get_by(channel_id=channel.id, guild_id=channel.guild.id,
                                                source=source.short_name)
            if len(sub) == 0:
                raise BadArgument(f"No subscription of {source.full_name} for channel {channel.mention} found.")

            elif len(sub) > 1:
                if isinstance(source, DataBasedSource):
                    raise BadArgument("There ware multiple subscriptions found. Try again with a data parameter.")
                else:
                    DOZER_LOGGER.error(f"More than one subscription of {source.full_name} for channel "
                                       f"{channel.mention} found when attempting to delete.")
                    raise BadArgument(f"More than one subscription of {source.full_name} for channel "
                                      f"{channel.mention} was found. Please contact the Dozer administrators for help.")

        await NewsSubscription.delete(id=sub[0].id)

        embed = discord.Embed(title=f"Subscription of channel #{channel.name} to {source.full_name} removed",
                              description="Posts from this source will no longer appear.")
        if isinstance(source, DataBasedSource):
            embed.add_field(name="Data", value=sub[0].data)

        embed.colour = discord.colour.Color.red()

        await ctx.send(embed=embed)

    remove.example_usage = """`{prefix}news remove #news cd` - Remove the subscription of Chief Delphi to #news
     `{prefix}news remove #reddit reddit frc` - Remove the subscription of /r/FRC to #reddit"""

    @news.command(name='sources')
    async def list_sources(self, ctx):
        """List all available sources to subscribe to."""
        embed = discord.Embed(title="All available sources to subscribe to.")

        embed.description = f"To subscribe to any of these sources, use the `{ctx.prefix}news add " \
                            f"<channel> <source name>` command."

        for source in self.sources.values():
            aliases = ", ".join(source.aliases)
            embed.add_field(name=f"{source.full_name}",
                            value=f"[{source.description}]({source.base_url})\n\nPossible Names: `{aliases}`",
                            inline=True)

        await ctx.send(embed=embed)

    list_sources.example_usage = "`{prefix}`news sources` - Get all available sources"

    @news.command(name='subscriptions', aliases=('subs', 'channels'))
    @guild_only()
    async def list_subscriptions(self, ctx, channel: discord.TextChannel = None):
        """List all subscriptions that the current server are subscribed to"""
        if channel is not None:
            results = await NewsSubscription.get_by(guild_id=ctx.guild.id, channel_id=ctx.channel.id)
        else:
            results = await NewsSubscription.get_by(guild_id=ctx.guild.id)

        if not results:
            embed = discord.Embed(title="News Subscriptions for {}".format(ctx.guild.name))
            embed.description = f"No news subscriptions found for this guild! Add one using `{self.bot.command_prefix}" \
                                f"news add <channel> <source>`"
            embed.colour = discord.Color.red()
            await ctx.send(embed=embed)
            return

        channels = {}
        for result in results:
            channel = ctx.bot.get_channel(result.channel_id)
            if channel is None:
                DOZER_LOGGER.error(f"Channel ID {result.channel_id} for subscription ID {result.id} not found.")
                continue

            try:
                channels[channel].append(result)
            except KeyError:
                channels[channel] = [result]

        embed = discord.Embed()
        embed.title = "News Subscriptions for {}".format(ctx.guild.name)
        embed.colour = discord.Color.dark_orange()
        for found_channel, lst in channels.items():
            subs = ""
            for sub in lst:
                subs += f"{sub.source}"
                if sub.data:
                    subs += f": {sub.data}"
                subs += "\n"
            embed.add_field(name=f"#{found_channel.name}", value=subs)
        await ctx.send(embed=embed)

    list_subscriptions.example_usage = """`{prefix}news subs` - Check all subscriptions in the current server
    `{prefix}news subs #news` - See all the subscriptions for #news"""

    @news.command()
    @dev_check()
    async def restart_loop(self, ctx):
        """Restart the news check loop"""
        self.get_new_posts.stop()
        self.get_new_posts.change_interval(minutes=self.bot.config['news']['check_interval'])
        self.get_new_posts.start()
        await ctx.send("Loop restarted.")

    restart_loop.example_usage = "`{prefix}news restart_loop` - Restart the news loop if you are a developer"

    @news.command()
    @dev_check()
    async def next_run(self, ctx):
        """Print out the next time the news check loop will run"""
        next_run = self.get_new_posts.next_iteration
        if next_run is None:
            await ctx.send(f"No next run scheduled. This likely means an exception occurred in the loop. Check this "
                           f"exception using {ctx.prefix}news get_exception, and then restart using "
                           f"{ctx.prefix}news restart_loop if appropriate. ")
        else:
            await ctx.send(f"Next run in "
                           f"{(next_run - datetime.datetime.now(datetime.timezone.utc)).total_seconds()} seconds.")

    next_run.example_usage = "`{prefix}news next_run` - Check the next time the loop runs if you are a developer"

    @news.command()
    @dev_check()
    async def get_exception(self, ctx):
        """If the news check loop has failed, print out the exception and traceback"""
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
                           f"determine the next time it's running with {ctx.prefix}news next_run")

    get_exception.example_usage = "`{prefix}news get_exception` - Get the exception that the loop failed with"


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

    def __init__(self, channel_id, guild_id, source, kind, data=None, sub_id=None):
        super().__init__()
        self.id = sub_id
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
            obj = NewsSubscription(sub_id=result.get("id"), channel_id=result.get("channel_id"),
                                   guild_id=result.get("guild_id"), source=result.get("source"),
                                   kind=result.get("kind"), data=result.get("data"))
            result_list.append(obj)
        return result_list
