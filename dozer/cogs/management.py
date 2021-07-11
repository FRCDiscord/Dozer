"""General, basic commands that are common for Discord bots"""
import inspect

import functools
import asyncio
import itertools
import logging
import math
from datetime import timedelta, timezone, datetime

import discord

from discord.ext.commands import guild_only, has_permissions, BadArgument
from discord.ext.tasks import loop
from dateutil import parser

from ._utils import *
from .general import blurple
from .. import db
from ..bot import DOZER_LOGGER

timezones = {"CDT": "UTC-5", "EST": "UTC-5", "EDT": "UTC-4"}


class Management(Cog):
    """A cog housing Guild management/utility commands."""

    @Cog.listener('on_ready')
    async def on_ready(self):
        """Restore time based event schedulers"""
        messages = await ScheduledMessages.get_by()
        DOZER_LOGGER.info("Restarting scheduled message send cycle")
        for message in messages:
            self.bot.loop.create_task(self.msg_timer(message))

    async def msg_timer(self, db_entry):
        delay = db_entry.time - datetime.now(tz=timezone.utc)
        print(delay.total_seconds())
        if delay.total_seconds() > 0:
            await asyncio.sleep(delay.total_seconds())
        await self.send_scheduled_msg(db_entry)
        await db_entry.delete()

    async def send_scheduled_msg(self, db_entry, channel_override=None):
        """Formats and sends scheduled message"""
        embed = discord.Embed(title=db_entry.header if db_entry.header else "Scheduled Message", description=db_entry.content)
        guild = self.bot.get_guild(db_entry.guild_id)
        channel = guild.get_channel(db_entry.channel_id if not channel_override else channel_override)
        embed.colour = blurple
        if db_entry.requester_id:
            name = await guild.fetch_member(db_entry.requester_id)
            embed.set_footer(text=f"Triggered by {name.display_name}")
        await channel.send(embed=embed)

    @command()
    @has_permissions(manage_messages=True)
    async def schedulesend(self, ctx, channel: discord.TextChannel, time, *, content):
        """Work in progress"""

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
            requester_id=ctx.author.id
        )
        await entry.update_or_add()

        self.bot.loop.create_task(self.msg_timer(entry))
        await ctx.send("Scheduled message saved\nPreview:")
        await self.send_scheduled_msg(entry, channel_override=ctx.message.channel.id)



class ScheduledMessages(db.DatabaseTable):
    """Stores messages that are scheduled to be sent"""
    __tablename__ = 'scheduled_messages'
    __uniques__ = 'id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            id serial, 
            guild_id bigint NOT NULL,
            channel_id bigint NOT NULL,
            requester_id bigint NULL, 
            time timestamptz NOT NULL,
            header text NULL,
            content text NOT NULL,
            PRIMARY KEY (id)
            )""")

    def __init__(self, guild_id, channel_id, time, content, header=None, requester_id=None):
        super().__init__()
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.requester_id = requester_id
        self.time = time
        self.header = header
        self.content = content

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = ScheduledMessages(guild_id=result.get("guild_id"), channel_id=result.get("channel_id"), header=result.get("header"),
                                    requester_id=result.get("member_id"), time=result.get("time"), content=result.get("content"))
            result_list.append(obj)
        return result_list


def setup(bot):
    """Adds the Management cog to the bot"""
    bot.add_cog(Management(bot))
