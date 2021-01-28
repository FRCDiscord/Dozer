"""Provides guild logging functions for Dozer."""
import logging
import asyncio
import datetime
import time

import discord
from discord.ext.commands import has_permissions

from ._utils import *
from .general import blurple
from .. import db

DOZER_LOGGER = logging.getLogger(__name__)


class Actionlog(Cog):
    """A cog to handle guild events tasks"""

    def __init__(self, bot):
        super().__init__(bot)
        self.edit_delete_config = db.ConfigCache(GuildMessageLog)
        self.bulk_delete_buffer = {}

    @staticmethod
    async def check_audit(guild, event_time=None):
        """Method for checking the audit log for events"""
        try:
            async for entry in guild.audit_logs(limit=1, before=event_time, action=discord.AuditLogAction.message_delete):
                return entry
        except discord.Forbidden:
            return None

    @staticmethod
    def format_join_leave(template: str, member: discord.Member):
        """Formats join leave message templates
        {guild} = guild name
        {user} = user's name plus discriminator ex. SnowPlow#5196
        {user_name} = user's name without discriminator
        {user_mention} = user's mention
        {user_id} = user's ID
        """
        if template:
            return template.format(guild=member.guild, user=str(member), user_name=member.name,
                                   user_mention=member.mention, user_id=member.id)
        else:
            return "{user_mention}\n{user} ({user_id})".format(user=str(member), user_mention=member.mention, user_id=member.id)

    @Cog.listener('on_member_join')
    async def on_member_join(self, member):
        """Logs that a member joined, with optional custom message"""
        config = await CustomJoinLeaveMessages.get_by(guild_id=member.guild.id)
        if len(config):
            channel = member.guild.get_channel(config[0].channel_id)
            if channel:
                embed = discord.Embed(color=0x00FF00)
                embed.set_author(name='Member Joined', icon_url=member.avatar_url_as(format='png', size=32))
                embed.description = self.format_join_leave(config[0].join_message, member)
                embed.set_footer(text="{} | {} members".format(member.guild.name, member.guild.member_count))
                try:
                    await channel.send(content=member.mention if config[0].ping else None, embed=embed)
                except discord.Forbidden:
                    DOZER_LOGGER.warning(f"Guild {member.guild}({member.guild.id}) has invalid permissions for join/leave logs")

    @Cog.listener('on_member_remove')
    async def on_member_remove(self, member):
        """Logs that a member left."""
        config = await CustomJoinLeaveMessages.get_by(guild_id=member.guild.id)
        if len(config):
            channel = member.guild.get_channel(config[0].channel_id)
            if channel:
                embed = discord.Embed(color=0xFF0000)
                embed.set_author(name='Member Left', icon_url=member.avatar_url_as(format='png', size=32))
                embed.description = self.format_join_leave(config[0].leave_message, member)
                embed.set_footer(text="{} | {} members".format(member.guild.name, member.guild.member_count))
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    DOZER_LOGGER.warning(f"Guild {member.guild}({member.guild.id}) has invalid permissions for join/leave logs")

    @Cog.listener()
    async def on_raw_bulk_message_delete(self, payload):
        """Log bulk message deletes"""
        guild = self.bot.get_guild(int(payload.guild_id))
        message_channel = self.bot.get_channel(int(payload.channel_id))
        message_ids = payload.message_ids
        cached_messages = payload.cached_messages

        message_log_channel = await self.edit_delete_config.query_one(guild_id=guild.id)
        if message_log_channel is not None:
            channel = guild.get_channel(message_log_channel.messagelog_channel)
            if channel is None:
                return
        else:
            return
        buffer = self.bulk_delete_buffer.get(message_channel.id)
        if buffer:
            self.bulk_delete_buffer[message_channel.id]["last_payload"] = time.time()
            self.bulk_delete_buffer[message_channel.id]["msg_ids"] += message_ids
            self.bulk_delete_buffer[message_channel.id]["msgs"] += cached_messages
            header_message = self.bulk_delete_buffer[message_channel.id]["header_message"]
            header_embed = discord.Embed(title="Bulk Message Delete", color=0xFF0000)
            deleted = self.bulk_delete_buffer[message_channel.id]["msg_ids"]
            cached = self.bulk_delete_buffer[message_channel.id]["msgs"]
            header_embed.description = f"{len(deleted)} Messages Deleted In: {message_channel.mention}\n" \
                                       f"Messages cached: {len(cached)}/{len(deleted)} \n" \
                                       f"Messages logged: *Currently Purging*"
            await header_message.edit(embed=header_embed)
        else:
            header_embed = discord.Embed(title="Bulk Message Delete", color=0xFF0000)
            header_embed.description = f"{len(message_ids)} Messages Deleted In: {message_channel.mention}\n" \
                                       f"Messages cached: {len(cached_messages)}/{len(message_ids)} \n" \
                                       f"Messages logged: *Currently Purging*"
            header_message = await channel.send(embed=header_embed)

            self.bulk_delete_buffer[message_channel.id] = {"last_payload": time.time(), "msg_ids": list(message_ids), "msgs": list(cached_messages),
                                                           "log_channel": channel, "header_message": header_message}

        await self.bulk_delete_log(message_channel)

    async def bulk_delete_log(self, message_channel):
        """Logs a bulk delete after the bot is finished the bulk delete"""
        buffer_entry = self.bulk_delete_buffer[message_channel.id]
        await asyncio.sleep(15)
        if buffer_entry["last_payload"] > time.time() - 15:
            return
        self.bulk_delete_buffer.pop(message_channel.id)
        message_ids = buffer_entry["msg_ids"]
        cached_messages = buffer_entry["msgs"]
        channel = buffer_entry["log_channel"]
        header_message = buffer_entry["header_message"]

        message_count = 0
        header_embed = discord.Embed(title="Bulk Message Delete", color=0xFF0000)
        header_embed.description = f"{len(message_ids)} Messages Deleted In: {message_channel.mention}\n" \
                                   f"Messages cached: {len(cached_messages)}/{len(message_ids)} \n" \
                                   f"Messages logged: *Currently Logging*"
        await header_message.edit(embed=header_embed)
        link = f"https://discordapp.com/channels/{header_message.guild.id}/{header_message.channel.id}/{header_message.id}"
        current_page = 1
        page_character_count = 0
        page_message_count = 0
        embed = discord.Embed(title="Bulk Message Delete", color=0xFF0000, timestamp=datetime.datetime.now(tz=datetime.timezone.utc))
        for message in sorted(cached_messages, key=lambda msg: msg.created_at):
            page_character_count += len(message.content[0:512]) + 3

            if page_character_count >= 5000 or page_message_count >= 25:
                embed.description = f"Messages {message_count}-{message_count + page_message_count} of [bulk delete]({link})"
                embed.set_footer(text=f"Page {current_page}")
                current_page += 1
                try:
                    await channel.send(embed=embed)
                except discord.HTTPException as e:
                    DOZER_LOGGER.debug(f"Bulk delete embed failed to send: {e}")
                embed = discord.Embed(title="Bulk Message Delete", color=0xFF0000, timestamp=datetime.datetime.now(tz=datetime.timezone.utc))
                page_character_count = len(message.content)
                message_count += page_message_count
                page_message_count = 0

            formatted_time = message.created_at.strftime("%b %d %Y %H:%M:%S")
            embed.add_field(name=f"{formatted_time}: {message.author}",
                            value="Message contained no content" if len(message.content) == 0 else message.content if len(message.content) < 512
                            else f"{message.content[0:512]}...", inline=False)
            page_message_count += 1
            if current_page > 15:
                break

        embed.description = f"Messages {message_count}-{message_count + page_message_count} of [bulk delete]({link})"
        embed.set_footer(text=f"Page {current_page}")
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as e:
            DOZER_LOGGER.debug(f"Bulk delete embed failed to send: {e}")
        header_embed.description = f"{len(message_ids)} Messages Deleted In: {message_channel.mention}\n" \
                                   f"Messages cached: {len(cached_messages)}/{len(message_ids)} \n" \
                                   f"Messages logged: {message_count}/{len(message_ids)}"
        await header_message.edit(embed=header_embed)

    @Cog.listener()
    async def on_raw_message_delete(self, payload):
        """When a message is deleted and its not in the bot cache, log it anyway."""
        if payload.cached_message:
            return
        guild = self.bot.get_guild(int(payload.guild_id))
        message_channel = self.bot.get_channel(int(payload.channel_id))
        message_id = int(payload.message_id)
        message_created = discord.Object(message_id).created_at
        embed = discord.Embed(title="Message Deleted",
                              description=f"Message Deleted In: {message_channel.mention}",
                              color=0xFF00F0, timestamp=message_created)
        embed.add_field(name="Message", value="N/A", inline=False)
        embed.set_footer(text=f"MessageID: {message_id}; Sent at")
        message_log_channel = await self.edit_delete_config.query_one(guild_id=guild.id)
        if message_log_channel is not None:
            channel = guild.get_channel(message_log_channel.messagelog_channel)
            if channel is not None:
                await channel.send(embed=embed)

    @Cog.listener('on_message_delete')
    async def on_message_delete(self, message):
        """When a message is deleted, log it."""
        if message.author == self.bot.user:
            return
        audit = await self.check_audit(message.guild)
        embed = discord.Embed(title="Message Deleted",
                              description=f"Message Deleted In: {message.channel.mention}\nSent by: {message.author.mention}",
                              color=0xFF0000, timestamp=message.created_at)
        embed.set_author(name=message.author, icon_url=message.author.avatar_url)
        if audit:
            if audit.target == message.author:
                audit_member = await message.guild.fetch_member(audit.user.id)
                embed.add_field(name="Message Deleted By: ", value=str(audit_member.mention), inline=False)
        if message.content:
            embed.add_field(name="Message Content:", value=message.content[0:1023], inline=False)
            if len(message.content) > 1024:
                embed.add_field(name="Message Content Continued:", value=message.content[1024:2000], inline=False)
        else:
            embed.add_field(name="Message Content:", value="N/A", inline=False)
        embed.set_footer(text=f"UserID: {message.author.id}")
        if message.attachments:
            embed.add_field(name="Attachments", value=", ".join([i.url for i in message.attachments]))
        message_log_channel = await self.edit_delete_config.query_one(guild_id=message.guild.id)
        if message_log_channel is not None:
            channel = message.guild.get_channel(message_log_channel.messagelog_channel)
            if channel is not None:
                await channel.send(embed=embed)

    @Cog.listener()
    async def on_raw_message_edit(self, payload):
        """Logs message edits that are not currently in the bots message cache"""
        if payload.cached_message:
            return
        mchannel = self.bot.get_channel(int(payload.channel_id))
        guild = mchannel.guild
        try:
            content = payload.data['content']
        except KeyError:
            content = None
        author = payload.data.get("author")
        if not author:
            return
        guild_id = guild.id
        channel_id = payload.channel_id
        user_id = author['id']
        if (self.bot.get_user(int(user_id))).bot:
            return  # Breakout if the user is a bot
        message_id = payload.message_id
        link = f"https://discordapp.com/channels/{guild_id}/{channel_id}/{message_id}"
        mention = f"<@!{user_id}>"
        avatar_link = f"http://cdn.discordapp.com/avatars/{user_id}/{author['avatar']}.webp?size=1024"
        embed = discord.Embed(title="Message Edited",
                              description=f"[MESSAGE]({link}) From {mention}\nEdited In: {mchannel.mention}", color=0xFFC400)
        embed.set_author(name=f"{author['username']}#{author['discriminator']}", icon_url=avatar_link)
        embed.add_field(name="Original", value="N/A", inline=False)
        if content:
            embed.add_field(name="Edited", value=content[0:1023], inline=False)
            if len(content) > 1024:
                embed.add_field(name="Edited Continued", value=content[1024:2000], inline=False)
        else:
            embed.add_field(name="Edited", value="N/A", inline=False)
        embed.set_footer(text=f"UserID: {user_id}")
        message_log_channel = await self.edit_delete_config.query_one(guild_id=guild.id)
        if message_log_channel is not None:
            channel = guild.get_channel(message_log_channel.messagelog_channel)
            if channel is not None:
                await channel.send(embed=embed)

    @Cog.listener('on_message_edit')
    async def on_message_edit(self, before, after):
        """Logs message edits."""
        if before.author.bot:
            return
        if after.edited_at is not None or before.edited_at is not None:
            # There is a reason for this. That reason is that otherwise, an infinite spam loop occurs
            guild_id = before.guild.id
            channel_id = before.channel.id
            user_id = before.author.id
            message_id = before.id
            link = f"https://discordapp.com/channels/{guild_id}/{channel_id}/{message_id}"
            embed = discord.Embed(title="Message Edited",
                                  description=f"[MESSAGE]({link}) From {before.author.mention}"
                                              f"\nEdited In: {before.channel.mention}", color=0xFFC400,
                                  timestamp=after.edited_at)
            embed.set_author(name=before.author, icon_url=before.author.avatar_url)
            if before.content:
                embed.add_field(name="Original", value=before.content[0:1023], inline=False)
                if len(before.content) > 1024:
                    embed.add_field(name="Original Continued", value=before.content[1024:2000], inline=False)
                embed.add_field(name="Edited", value=after.content[0:1023], inline=False)
                if len(after.content) > 1024:
                    embed.add_field(name="Edited Continued", value=after.content[1024:2000], inline=False)
            else:
                embed.add_field(name="Original", value="N/A", inline=False)
                embed.add_field(name="Edited", value="N/A", inline=False)
            embed.set_footer(text=f"UserID: {user_id}")
            if after.attachments:
                embed.add_field(name="Attachments", value=", ".join([i.url for i in before.attachments]))
            message_log_channel = await self.edit_delete_config.query_one(guild_id=before.guild.id)
            if message_log_channel is not None:
                channel = before.guild.get_channel(message_log_channel.messagelog_channel)
                if channel is not None:
                    await channel.send(embed=embed)

    @command()
    @has_permissions(administrator=True)
    async def messagelogconfig(self, ctx, channel_mentions: discord.TextChannel):
        """Set the modlog channel for a server by passing the channel id"""
        config = await GuildMessageLog.get_by(guild_id=ctx.guild.id)
        if len(config) != 0:
            config = config[0]
            config.name = ctx.guild.name
            config.messagelog_channel = channel_mentions.id
        else:
            config = GuildMessageLog(guild_id=ctx.guild.id, messagelog_channel=channel_mentions.id, name=ctx.guild.name)
        await config.update_or_add()
        self.edit_delete_config.invalidate_entry(id=ctx.guild.id)
        await ctx.send(ctx.message.author.mention + ', messagelog settings configured!')

    messagelogconfig.example_usage = """
        `{prefix}messagelogconfig #orwellian-dystopia` - set a channel named #orwellian-dystopia to log message edits/deletions
        """

    @group(invoke_without_command=True)
    @has_permissions(administrator=True)
    async def memberlogconfig(self, ctx):
        """Command group to configure Join/Leave logs"""
        config = await CustomJoinLeaveMessages.get_by(guild_id=ctx.guild.id)
        embed = discord.Embed(title=f"Join/Leave configuration for {ctx.guild}", color=blurple)
        if len(config):
            channel = ctx.guild.get_channel(config[0].channel_id)
            embed.add_field(name="Message Channel", value=channel.mention if channel else "None")
            embed.add_field(name="Ping on join", value=config[0].ping)
            embed.add_field(name="Join template", value=config[0].join_message, inline=False)
            embed.add_field(name="Join Example", value=self.format_join_leave(config[0].join_message, ctx.author))
            embed.add_field(name="Leave template", value=config[0].leave_message, inline=False)
            embed.add_field(name="Leave Example", value=self.format_join_leave(config[0].leave_message, ctx.author))
            await ctx.send(embed=embed)
        else:
            await ctx.send("This guild has no member log configured")

    memberlogconfig.example_usage = """
    `{prefix}memberlogconfig setchannel channel`: Sets the member log channel 
    `{prefix}memberlogconfig toggleping`: Toggles whenever members are pinged upon joining the guild
    `{prefix}memberlogconfig setjoinmessage template`: Sets join template
    `{prefix}memberlogconfig setleavemessage template`: Sets leave template
    `{prefix}memberlogconfig help`: Returns the template formatting key
    """

    @memberlogconfig.command()
    @has_permissions(manage_guild=True)
    async def setchannel(self, ctx, channel: discord.TextChannel):
        """Configure join/leave channel"""
        config = CustomJoinLeaveMessages(
            guild_id=ctx.guild.id,
            channel_id=channel.id
        )
        await config.update_or_add()
        e = discord.Embed(color=blurple)
        e.add_field(name='Success!', value=f"Join/Leave log channel has been set to {channel.mention}")
        e.set_footer(text='Triggered by ' + ctx.author.display_name)
        await ctx.send(embed=e)

    @memberlogconfig.command()
    @has_permissions(manage_guild=True)
    async def toggleping(self, ctx):
        """Toggles whenever a new member gets pinged on join"""
        config = await CustomJoinLeaveMessages.get_by(guild_id=ctx.guild.id)
        if len(config):
            config[0].ping = not config[0].ping
        else:
            config[0] = CustomJoinLeaveMessages(guild_id=ctx.guild.id, ping=True)
        await config[0].update_or_add()

        e = discord.Embed(color=blurple)
        e.add_field(name='Success!', value=f"Ping on join is set to: {config[0].ping}")
        e.set_footer(text='Triggered by ' + ctx.author.display_name)
        await ctx.send(embed=e)

    @memberlogconfig.command()
    @has_permissions(manage_guild=True)
    async def setjoinmessage(self, ctx, *, template: str = None):
        """Configure custom join message template"""
        e = discord.Embed(color=blurple)
        e.set_footer(text='Triggered by ' + ctx.author.display_name)
        if template:
            config = CustomJoinLeaveMessages(
                guild_id=ctx.guild.id,
                join_message=template
            )
            e.add_field(name='Success!', value=f"Join message template has been set to\n{template}")
        else:
            config = CustomJoinLeaveMessages(
                guild_id=ctx.guild.id,
                join_message=CustomJoinLeaveMessages.nullify
            )
            e.add_field(name='Success!', value="Join message has been set to default")
        await config.update_or_add()
        await ctx.send(embed=e)

    @memberlogconfig.command()
    @has_permissions(manage_guild=True)
    async def setleavemessage(self, ctx, *, template=None):
        """Configure custom leave message template"""
        e = discord.Embed(color=blurple)
        e.set_footer(text='Triggered by ' + ctx.author.display_name)
        if template:
            config = CustomJoinLeaveMessages(
                guild_id=ctx.guild.id,
                leave_message=template
            )
            e.add_field(name='Success!', value=f"Leave message template has been set to\n{template}")
        else:
            config = CustomJoinLeaveMessages(
                guild_id=ctx.guild.id,
                leave_message=CustomJoinLeaveMessages.nullify
            )
            e.add_field(name='Success!', value="Leave message has been set to default")
        await config.update_or_add()
        await ctx.send(embed=e)

    @memberlogconfig.command()
    @has_permissions(manage_guild=True)
    async def disable(self, ctx):
        """Disables Join/Leave logging"""
        e = discord.Embed(color=blurple)
        e.set_footer(text='Triggered by ' + ctx.author.display_name)
        config = CustomJoinLeaveMessages(
            guild_id=ctx.guild.id,
            channel_id=CustomJoinLeaveMessages.nullify
        )
        await config.update_or_add()
        e.add_field(name='Success!', value="Join/Leave logs have been disabled")
        await ctx.send(embed=e)

    @memberlogconfig.command()
    @has_permissions(manage_guild=True)
    async def help(self, ctx):  # I cannot put formatting example in example_usage because then it trys to format the example
        """Displays message formatting key"""
        e = discord.Embed(color=blurple)
        e.set_footer(text='Triggered by ' + ctx.author.display_name)
        e.description = """
        `{guild}` = guild name
        `{user}` = user's name plus discriminator ex. SnowPlow#5196
        `{user_name}` = user's name without discriminator
        `{user_mention}` = user's mention
        `{user_id}` = user's ID
        """
        await ctx.send(embed=e)


class CustomJoinLeaveMessages(db.DatabaseTable):
    """Holds custom join leave messages"""
    __tablename__ = 'memberlogconfig'
    __uniques__ = 'guild_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY NOT NULL,	            
            memberlog_channel bigint NOT NULL,	   
            name varchar NOT NULL
            )""")

    def __init__(self, guild_id, channel_id=None, ping=None, join_message=None, leave_message=None):
        super().__init__()
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.ping = ping
        self.join_message = join_message
        self.leave_message = leave_message

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = CustomJoinLeaveMessages(guild_id=result.get("guild_id"), channel_id=result.get("channel_id"), ping=result.get("ping"),
                                          join_message=result.get("join_message"), leave_message=result.get("leave_message"))
            result_list.append(obj)
        return result_list

    async def version_1(self):
        """DB migration v1"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            alter table memberlogconfig rename column memberlog_channel to channel_id;
            alter table memberlogconfig alter column channel_id drop not null;
            alter table {self.__tablename__} drop column IF EXISTS name;
            alter table {self.__tablename__}
                add IF NOT EXISTS ping boolean default False;
            alter table {self.__tablename__}
                add IF NOT EXISTS join_message text default null;
            alter table {self.__tablename__}
                add IF NOT EXISTS leave_message text default null;
            """)
            
    __versions__ = [version_1]


class GuildMessageLog(db.DatabaseTable):
    """Holds config info for message logs"""
    __tablename__ = 'messagelogconfig'
    __uniques__ = 'guild_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY NOT NULL,
            name varchar NOT NULL,
            messagelog_channel bigint NOT NULL
            )""")

    def __init__(self, guild_id, name, messagelog_channel):
        super().__init__()
        self.guild_id = guild_id
        self.name = name
        self.messagelog_channel = messagelog_channel

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = GuildMessageLog(guild_id=result.get("guild_id"), name=result.get("name"),
                                  messagelog_channel=result.get("messagelog_channel"))
            result_list.append(obj)
        return result_list


def setup(bot):
    """Adds the actionlog cog to the bot."""
    bot.add_cog(Actionlog(bot))
