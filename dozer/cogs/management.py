"""General, basic commands that are common for Discord bots"""

import asyncio
import logging
import math

import humanize
from datetime import timezone, datetime

import discord
from dateutil import parser
from discord.ext.commands import has_permissions, CommandInvokeError

from ._utils import *
from .general import blurple
from .. import db

timezones = {"CDT": "UTC-5", "EST": "UTC-5", "EDT": "UTC-4"}

DOZER_LOGGER = logging.getLogger(__name__)


class Management(Cog):
    """A cog housing Guild management/utility commands."""
    def __init__(self, bot):
        super().__init__(bot)
        self.started_timers = False
        self.timers = {}

    @Cog.listener('on_ready')
    async def on_ready(self):
        """Restore time based event schedulers"""
        messages = await ScheduledMessages.get_by()
        started = 0
        if not self.started_timers:
            for message in messages:
                task = self.bot.loop.create_task(self.msg_timer(message))
                self.timers[message.request_id] = task
                started += 1
            self.started_timers = True
            DOZER_LOGGER.info(f"Started {started}/{len(messages)} scheduled messages")
        else:
            DOZER_LOGGER.info(f"Client Resumed: Timers still running")

    async def msg_timer(self, db_entry):
        delay = db_entry.time - datetime.now(tz=timezone.utc)
        if delay.total_seconds() > 0:
            await asyncio.sleep(delay.total_seconds())
        await self.send_scheduled_msg(db_entry)
        await db_entry.delete(request_id=db_entry.request_id)

    async def send_scheduled_msg(self, db_entry, channel_override=None):
        """Formats and sends scheduled message"""
        embed = discord.Embed(title=db_entry.header if db_entry.header else "Scheduled Message", description=db_entry.content)
        guild = self.bot.get_guild(db_entry.guild_id)
        channel = guild.get_channel(db_entry.channel_id if not channel_override else channel_override)
        embed.colour = blurple
        if db_entry.requester_id:
            name = await guild.fetch_member(db_entry.requester_id)
            embed.set_footer(text=f"Author: {name.display_name}")
        await channel.send(embed=embed)

    @group(invoke_without_command=True)
    @has_permissions(manage_messages=True)
    async def schedulesend(self, ctx):
        """Allows a message to be sent at a particular time
        Supported timezones= EST/EDT, CST/CDT, UTC"""

    @schedulesend.command()
    @has_permissions(manage_messages=True)
    async def add(self, ctx, channel: discord.TextChannel, time, *, content):
        """Allows a message to be sent at a particular time
        Supported timezones= EST/EDT, CST/CDT, UTC
        """

        send_time = parser.parse(time, tzinfos=timezones)
        content = content.split("-/-", 1)
        message = content[1] if len(content) == 2 else content[0]
        header = content[0] if len(content) == 2 else None
        entry = ScheduledMessages(
            guild_id=ctx.guild.id,
            channel_id=channel.id,
            time=send_time,
            content=message,
            header=header,
            requester_id=ctx.author.id,
            request_id=ctx.message.id
        )
        await entry.update_or_add()
        task = self.bot.loop.create_task(self.msg_timer(entry))
        self.timers[entry.request_id] = task
        await ctx.send("Scheduled message saved\nPreview:")
        await self.send_scheduled_msg(entry, channel_override=ctx.message.channel.id)

    @schedulesend.command()
    @has_permissions(manage_messages=True)
    async def delete(self, ctx, entry_id: int):
        """Delete a scheduled message"""
        entries = await ScheduledMessages.get_by(entry_id=entry_id)
        e = discord.Embed(color=blurple)
        if len(entries) > 0:
            response = await ScheduledMessages.delete(request_id=entries[0].request_id)
            task = self.timers[entries[0].request_id]
            task.cancel()
            if response.split(" ", 1)[1] == "1":
                e.add_field(name='Success', value=f"Deleted entry with ID: {entry_id} and cancelled planned send")
                e.set_footer(text='Triggered by ' + ctx.author.display_name)
                await ctx.send(embed=e)
            else:
                raise CommandInvokeError("Unable to delete db entry")
        else:
            e.add_field(name='Error', value=f"No entry with ID: {entry_id} found")
            e.set_footer(text='Triggered by ' + ctx.author.display_name)
            await ctx.send(embed=e)

    @schedulesend.command()
    @has_permissions(manage_messages=True)
    async def list(self, ctx):
        """Displays currently scheduled messages"""
        messages = await ScheduledMessages.get_by(guild_id=ctx.guild.id)
        pages = []
        for page_num, page in enumerate(chunk(messages, 3)):
            embed = discord.Embed(title=f"Currently scheduled messages for {ctx.guild}")
            pages.append(embed)
            for message in page:
                requester = await ctx.guild.fetch_member(message.requester_id)
                embed.add_field(name=f"ID: {message.entry_id}", value=f"Channel: <#{message.channel_id}>"
                                                                      f"\nTime: {message.time} UTC"
                                                                      f"\nAuthor: {requester.mention}", inline=False)
                embed.add_field(name=f"Header: {message.header}", value=message.content, inline=False)
                embed.set_footer(text=f"Page {page_num + 1} of {math.ceil(len(messages) / 3)}")
        await paginate(ctx, pages)


class ScheduledMessages(db.DatabaseTable):
    """Stores messages that are scheduled to be sent"""
    __tablename__ = 'scheduled_messages'
    __uniques__ = 'entry_id, request_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            entry_id serial,
            request_id bigint UNIQUE NOT NULL, 
            guild_id bigint NOT NULL,
            channel_id bigint NOT NULL,
            requester_id bigint NULL, 
            time timestamptz NOT NULL,
            header text NULL,
            content text NOT NULL,
            PRIMARY KEY (entry_id, request_id)
            )""")

    def __init__(self, guild_id, channel_id, time, content, request_id, header=None, requester_id=None, entry_id=None):
        super().__init__()
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.requester_id = requester_id
        self.request_id = request_id
        self.time = time
        self.header = header
        self.content = content
        self.entry_id = entry_id

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = ScheduledMessages(guild_id=result.get("guild_id"), channel_id=result.get("channel_id"), header=result.get("header"),
                                    requester_id=result.get("requester_id"), time=result.get("time"), content=result.get("content"),
                                    entry_id=result.get("entry_id"), request_id=result.get("request_id"))
            result_list.append(obj)
        return result_list


def setup(bot):
    """Adds the Management cog to the bot"""
    bot.add_cog(Management(bot))
