"""General, basic commands that are common for Discord bots"""

import asyncio
import json
import math
import os
from datetime import timezone, datetime
from typing import List

import discord
from dateutil import parser
from discord.ext.commands import has_permissions, BadArgument
from discord.utils import escape_markdown
from loguru import logger

from dozer.bot import Dozer
from dozer.context import DozerContext
from ._utils import *
from .general import blurple
from .. import db

TIMEZONE_FILE = "timezones.json"


class Management(Cog):
    """A cog housing Guild management/utility commands."""

    def __init__(self, bot: Dozer):
        super().__init__(bot)
        self.started_timers = False
        self.timers = {}
        if os.path.isfile(TIMEZONE_FILE):
            logger.info("Loaded timezone configurations")
            with open(TIMEZONE_FILE) as f:
                self.timezones = json.load(f)
        else:
            logger.error("Unable to load timezone configurations")
            self.timezones = {}

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
            logger.info(f"Started {started}/{len(messages)} scheduled messages")
        else:
            logger.info("Client Resumed: Timers still running")

    async def msg_timer(self, db_entry):
        """Holds the futures for sending a message"""
        delay = db_entry.time - datetime.now(tz=timezone.utc)
        if delay.total_seconds() > 0:
            await asyncio.sleep(delay.total_seconds())
        await self.send_scheduled_msg(db_entry)
        await db_entry.delete(request_id=db_entry.request_id)

    async def send_scheduled_msg(self, db_entry, channel_override: int = None):
        """Formats and sends scheduled message"""
        embed = discord.Embed(title=db_entry.header if db_entry.header else "Scheduled Message",
                              description=db_entry.content)
        guild = self.bot.get_guild(db_entry.guild_id)
        if not guild:
            logger.warning(
                f"Attempted to schedulesend message in guild({db_entry.guild_id}); Guild no longer exist")
            return
        channel = guild.get_channel(db_entry.channel_id if not channel_override else channel_override)
        if not channel:
            logger.warning(f"Attempted to schedulesend message in guild({guild}), channel({db_entry.channel_id});"
                           f" Channel no longer exist")
            return
        embed.colour = blurple
        perms = channel.permissions_for(guild.me)
        if db_entry.requester_id:
            name = await guild.fetch_member(db_entry.requester_id)
            embed.set_footer(text=f"Author: {escape_markdown(name.display_name)}")
        if perms.send_messages:
            await channel.send(embed=embed)
        else:
            logger.warning((f"Attempted to schedulesend message in guild({guild}:{guild.id}), channel({channel});"
                            f" Client lacks send permissions"))

    @group(invoke_without_command=True)
    @has_permissions(manage_messages=True)
    async def schedulesend(self, ctx: DozerContext):
        """Allows a message to be sent at a particular time
        Commands: add, delete, list
        """
        await ctx.send("Allows a message to be sent at a particular time\nCommands: add, delete, list")

    @schedulesend.command()
    @has_permissions(manage_messages=True)
    async def add(self, ctx: DozerContext, channel: discord.TextChannel, time, *, content):
        """Allows a message to be sent at a particular time
        Headers are distinguished by the characters `-/-`
        """
        perms = channel.permissions_for(ctx.guild.me)
        if not perms.send_messages:
            raise BadArgument(f"Dozer does not have permissions to send messages in {channel.mention}")
        try:
            send_time = parser.parse(time, tzinfos=self.timezones)
        except ValueError:
            raise BadArgument("Unknown Date Format")
        except OverflowError:
            raise BadArgument("Date exceeds max value")
        if send_time.tzinfo is None:
            await ctx.send("```Warning! Unknown timezone entered, defaulting to UTC```")
            send_time.replace(tzinfo=timezone.utc)
        content = content.split("-/-", 1)
        message = content[1] if len(content) == 2 else content[0]
        header = content[0] if len(content) == 2 else None
        if header is not None:
            if len(header) > 256:  # message does not need a check as description max char is higher than max message length of 4000
                await ctx.send("```Warning! Header larger than max 256 characters, header has been truncated```")
        entry = ScheduledMessages(
            guild_id=ctx.guild.id,
            channel_id=channel.id,
            time=send_time,
            content=message,
            header=header[:256],
            requester_id=ctx.author.id,
            request_id=ctx.message.id
        )
        await entry.update_or_add()
        entries = await ScheduledMessages.get_by(request_id=entry.request_id)
        entry = entries[0]
        task = self.bot.loop.create_task(self.msg_timer(entry))
        self.timers[entry.request_id] = task
        await ctx.send(f"Scheduled message(ID: {entry.entry_id}) saved, and will be sent in {channel.mention} on"
                       f" {send_time.strftime('%B %d %H:%M%z %Y')}\nMessage preview:")
        await self.send_scheduled_msg(entry, channel_override=ctx.message.channel.id)

    add.example_usage = """
    `{prefix}schedulesend add #announcments "1/0/1970 0:00:00 GMT" Epoch -/- 00000`: Dozer will send a message on the unix epoch in #announcments
    """

    @schedulesend.command()
    @has_permissions(manage_messages=True)
    async def delete(self, ctx: DozerContext, entry_id: int):
        """Delete a scheduled message"""
        entries = await ScheduledMessages.get_by(entry_id=entry_id)
        e = discord.Embed(color=blurple)
        if len(entries) > 0:
            response = await ScheduledMessages.delete(request_id=entries[0].request_id)
            task = self.timers.pop(entries[0].request_id)
            task.cancel()
            if response.split(" ", 1)[1] == "1":
                e.add_field(name='Success', value=f"Deleted entry with ID: {entry_id} and cancelled planned send")
                e.set_footer(text='Triggered by ' + escape_markdown(ctx.author.display_name))
                await ctx.send(embed=e)
            elif response.split(" ", 1)[1] == "0":
                raise Exception("Requested row not deleted")

        else:
            e.add_field(name='Error', value=f"No entry with ID: {entry_id} found")
            e.set_footer(text='Triggered by ' + escape_markdown(ctx.author.display_name))
            await ctx.send(embed=e)

    delete.example_usage = """
    `{prefix}schedulesend delete 5`: Deletes the scheduled message with the ID of 5
    """

    @schedulesend.command()
    @has_permissions(manage_messages=True)
    async def list(self, ctx: DozerContext):
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

    list.example_usage = """
    `{prefix}schedulesend list`: Lists all scheduled messages for the current guild
    """


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

    def __init__(self, guild_id: int, channel_id: int, time: datetime.time, content: str, request_id: int,
                 header: str = None, requester_id: int = None, entry_id: int = None):
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
    async def get_by(cls, **kwargs) -> List["ScheduledMessages"]:
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = ScheduledMessages(guild_id=result.get("guild_id"), channel_id=result.get("channel_id"),
                                    header=result.get("header"),
                                    requester_id=result.get("requester_id"), time=result.get("time"),
                                    content=result.get("content"),
                                    entry_id=result.get("entry_id"), request_id=result.get("request_id"))
            result_list.append(obj)
        return result_list


async def setup(bot):
    """Adds the Management cog to the bot"""
    await bot.add_cog(Management(bot))
