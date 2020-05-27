import logging
from asyncio import CancelledError, InvalidStateError
from datetime import timezone
import traceback

from discord.ext import tasks
from discord.ext.commands import guild_only, check, NotOwner

from ._utils import *
from .. import db
from ..sources import *

DOZER_LOGGER = logging.getLogger('dozer')
DOZER_LOGGER.level = logging.INFO


class News(Cog):
    enabled_sources = [FRCBlogPosts, CDLatest, TestSource]
    kinds = ['plain', 'embed']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.updated = True
        self.sources = {}

    @Cog.listener('on_ready')
    async def startup(self):
        self.sources = {}
        for source in self.enabled_sources:
            self.sources[source.short_name] = source(aiohttp_session=aiohttp.ClientSession())
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
                DOZER_LOGGER.debug(f"Skipping source {source.source_name} due to no subscriptions")
                continue
            if source.accepts_data:
                if source.needs_data and not source.data:
                    DOZER_LOGGER.debug(f"Skipping source {source.full_name} due to no data")
                    continue
                raise NotImplementedError

            else:
                channels = {}
                for sub in subs:
                    channel = self.bot.get_channel(sub.channel_id)
                    if channel is None:
                        DOZER_LOGGER.error(f"Channel {sub.channel_id} (sub ID {sub.id}) returned None. Removing sub "
                                           f"from Sub list.")
                        await NewsSubscription.delete(id=sub.id)
                        continue
                    channels[channel] = sub.kind
                posts = await source.get_new_posts()
                for (channel, kind) in channels.items():
                    if kind == 'embed':
                        for embed in posts['source']['embed']:
                            await channel.send(embed=embed)
                    elif kind == 'plain':
                        for post in posts['source']['plain']:
                            await channel.send(post)

        next_run = self.get_new_posts.next_iteration
        DOZER_LOGGER.info(f"Done with getting news. Next run in "
                          f"{(next_run - datetime.datetime.now(timezone.utc)).total_seconds()}"
                          f" seconds.")

    # Whenever version 1.4.0 of discord.py comes out, this can be uncommented. For now, use the get_exception commmand
    # @get_new_posts.error()
    # async def log_exception(self, exception):
    #     DOZER_LOGGER.error(exception)

    @group(invoke_without_command=True)
    @guild_only()
    async def news(self, ctx):
        """Manage news subscriptions for the current server"""
        results = await NewsSubscription.get_by(guild_id=ctx.guild.id)

        if not results:
            embed = discord.Embed(title="News Subscriptions for {}".format(ctx.guild.name))
            embed.description = "No news subscriptions found for this guild! Add one using `{}news add <channel> " \
                                "<source>`".format(
                ctx.bot.command_prefix)
            embed.color = discord.Color.red()
            await ctx.send(embed=embed)
            return

        fmt = "{bot.get_channel(0.channel_id).name}: {source}"  # TODO: do this by channel
        news_text = '\n'.join(map(fmt.format, results))

        embed = discord.Embed()
        embed.title = "News Subscriptions for {}".format(ctx.guild.name)
        embed.add_field(name="Filters", value=news_text)
        embed.color = discord.Color.dark_orange()
        await ctx.send(embed=embed)

    @news.command()
    @guild_only()
    async def add(self, ctx, channel: discord.TextChannel,  source, kind='embed', data=None):
        """Add a new subscription of a given source to a channel."""

        chosen_source = None
        for enabled_source in self.sources.values():
            if source in enabled_source.aliases:
                chosen_source = enabled_source
            break
        if chosen_source is None:
            await ctx.send(f"No source under the name {source} found.")
            return

        if data is not None and not chosen_source.accepts_data:
            await ctx.send(f"The source {source} does not accept extra data.")
            return

        if data is None and chosen_source.needs_data:
            await ctx.send(f"The source {source} needs extra data.")
            return

        if channel is None:
            await ctx.send(f"Cannot find the channel {channel}.")
            return

        if not channel.permissions_for(ctx.me).send_messages:
            await ctx.send(f"I don't have permission to post in f{channel.mention}.")
            return

        if kind not in self.kinds:
            await ctx.send(f"{kind} is not a accepted kind of post. Accepted kinds are {', '.join(self.kinds)}")
            return

        search_exists = await NewsSubscription.get_by(channel_id=channel.id, source=chosen_source.short_name)

        data_found = []
        for existing in search_exists:
            data_found += existing.data
        if data_found:
            if data[0] is None:
                await ctx.send(f"There is already a subscription of {source} for {channel.mention}")
                return
            else:
                if data in data_found:
                    await ctx.send(f"There is already a subscription of {source} with data {data} in {channel.mention}")
                    return

        if chosen_source.accepts_data:
            try:
                chosen_source.add_data(data)
            except DataBasedSource.InvalidDataException as e:
                await ctx.send(f"Data {data} is invalid. {e.reason}")
                return

        new_sub = NewsSubscription(channel_id=channel.id, guild_id=channel.guild.id, source=chosen_source.short_name,
                                   kind=kind, data=data)
        await new_sub.update_or_add()

    @news.command()
    async def list(self, ctx):
        embed = discord.Embed(title="All available sources to subscribe to.")

        embed.description = f"To subscribe to any of these sources, use the `{self.bot.config['prefix']}news add` command."

        for source in self.sources.values():
            aliases = ", ".join(source.aliases)
            embed.add_field(name=f"{source.full_name}",
                            value=f"[{source.description}]({source.base_url})\n\nPossible Names: `{aliases}`",
                            inline=True)

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
                           f"{(next_run - datetime.datetime.now(timezone.utc)).total_seconds()} seconds.")

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
