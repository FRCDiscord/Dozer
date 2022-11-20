"""Provides guild logging functions for Dozer."""
import asyncio
import math
import time
import datetime
from typing import TYPE_CHECKING, List, Set, Optional

import discord
from discord import Guild, AuditLogAction, Member, Message, Embed, AuditLogEntry
from discord.ext.commands import has_permissions, BadArgument
from discord.utils import escape_markdown
from loguru import logger

from dozer.context import DozerContext
from ._utils import *
from .general import blurple
from .. import db

if TYPE_CHECKING:
    from dozer import Dozer


async def embed_paginatorinator(content_name: str, embed: Embed, text: str):
    """Chunks up embed sections to fit within 1024 characters"""
    required_chunks = math.ceil(len(text) / 1024)
    c_embed = embed.copy()
    c_embed.add_field(name=content_name, value=text[0:1023], inline=False)
    for n in range(1, required_chunks):
        c_embed.add_field(name=f"{content_name} Continued ({n})", value=text[1024 * n:(1024 * (n + 1)) - 1],
                          inline=False)
    return c_embed


class Actionlog(Cog):
    """A cog to handle guild events tasks"""

    def __init__(self, bot: "Dozer"):
        super().__init__(bot)
        self.edit_delete_config: db.ConfigCache = db.ConfigCache(GuildMessageLog)
        self.bulk_delete_buffer = {}

    @staticmethod
    async def check_audit(guild: Guild, event_type: AuditLogAction, event_time: Optional[datetime] = None):
        """Method for checking the audit log for events"""
        try:
            async for entry in guild.audit_logs(limit=1, after=event_time,
                                                action=event_type):
                return entry
        except discord.Forbidden:
            return None

    @Cog.listener('on_member_join')
    async def on_member_join(self, member: Member):
        """Logs that a member joined, with optional custom message"""
        join_leave_config: List[CustomJoinLeaveMessages] = await CustomJoinLeaveMessages.get_by(guild_id=member.guild.id)
        new_members_config: List[GuildNewMember] = await GuildNewMember.get_by(guild_id=member.guild.id)
        if len(new_members_config) == 0 and len(join_leave_config) == 0:
            await send_log(member)
        else:
            if len(new_members_config) > 0 and new_members_config[0].require_team:
                return
            elif len(join_leave_config) > 0 and join_leave_config[0].send_on_verify:
                return
            else:
                await send_log(member)

    @Cog.listener('on_member_remove')
    async def on_member_remove(self, member: Member):
        """Logs that a member left."""
        config = await CustomJoinLeaveMessages.get_by(guild_id=member.guild.id)
        if len(config):
            channel = member.guild.get_channel(config[0].channel_id)
            if channel:
                embed: Embed = Embed(color=0xFF0000)
                embed.set_author(name='Member Left', icon_url=member.avatar.replace(format='png', size=32))
                embed.description = format_join_leave(config[0].leave_message, member)
                embed.set_footer(text="{} | {} members".format(member.guild.name, member.guild.member_count))
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    logger.warning(
                        f"Guild {member.guild}({member.guild.id}) has invalid permissions for join/leave logs")

    @Cog.listener("on_member_update")
    async def on_member_update(self, before: Member, after: Member):
        """Called whenever a member gets updated"""
        if before.nick != after.nick:
            await self.on_nickname_change(before, after)

    async def on_nickname_change(self, before: Member, after: Member):
        """The log handler for when a user changes their nicknames"""
        audit: Optional[AuditLogEntry] = await self.check_audit(after.guild, discord.AuditLogAction.member_update)

        embed: Embed = Embed(title="Nickname Changed",
                             color=0x00FFFF)
        embed.set_author(name=after, icon_url=after.avatar)
        embed.add_field(name="Before", value=before.nick, inline=False)
        embed.add_field(name="After", value=after.nick, inline=False)

        if audit:
            if audit.target == after:
                audit_member = await after.guild.fetch_member(audit.user.id)
                embed.description = f"Nickname Changed By: {audit_member.mention}"

        embed.set_footer(text=f"UserID: {after.id}")
        message_log_channel = await self.edit_delete_config.query_one(guild_id=after.guild.id)
        if message_log_channel is not None:
            channel = after.guild.get_channel(message_log_channel.messagelog_channel)
            if channel is not None:
                await channel.send(embed=embed)
        await self.check_nickname_lock(before, after)

    @staticmethod
    async def check_nickname_lock(before: Member, after: Member):
        """The handler for checking if a member is allowed to change their nickname"""
        results: List[NicknameLock] = await NicknameLock.get_by(guild_id=after.guild.id, member_id=after.id)
        if results:
            while time.time() <= results[0].timeout:
                await asyncio.sleep(10)  # prevents nickname update spam

            if results[0].locked_name != after.display_name:
                try:
                    await after.edit(nick=results[0].locked_name)
                except discord.Forbidden:
                    return
                results[0].timeout = time.time() + 10
                await results[0].update_or_add()
                await after.send(f"{after.mention}, you do not have nickname change perms in **{after.guild}** "
                                 f"your nickname has been reverted to **{results[0].locked_name}**")

    @Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent):
        """Log bulk message deletes"""
        guild: Guild = self.bot.get_guild(int(payload.guild_id))
        message_channel: discord.TextChannel = self.bot.get_channel(int(payload.channel_id))
        message_ids: Set[int] = payload.message_ids
        cached_messages: List[Message] = payload.cached_messages

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
            header_embed = Embed(title="Bulk Message Delete", color=0xFF0000)
            deleted = self.bulk_delete_buffer[message_channel.id]["msg_ids"]
            cached = self.bulk_delete_buffer[message_channel.id]["msgs"]
            header_embed.description = f"{len(deleted)} Messages Deleted In: {message_channel.mention}\n" \
                                       f"Messages cached: {len(cached)}/{len(deleted)} \n" \
                                       f"Messages logged: *Currently Purging*"
            await header_message.edit(embed=header_embed)
        else:
            header_embed = Embed(title="Bulk Message Delete", color=0xFF0000)
            header_embed.description = f"{len(message_ids)} Messages Deleted In: {message_channel.mention}\n" \
                                       f"Messages cached: {len(cached_messages)}/{len(message_ids)} \n" \
                                       f"Messages logged: *Currently Purging*"
            header_message = await channel.send(embed=header_embed)

            self.bulk_delete_buffer[message_channel.id] = {"last_payload": time.time(), "msg_ids": list(message_ids),
                                                           "msgs": list(cached_messages),
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
        header_embed = Embed(title="Bulk Message Delete", color=0xFF0000)
        header_embed.description = f"{len(message_ids)} Messages Deleted In: {message_channel.mention}\n" \
                                   f"Messages cached: {len(cached_messages)}/{len(message_ids)} \n" \
                                   f"Messages logged: *Currently Logging*"
        await header_message.edit(embed=header_embed)
        link = f"https://discordapp.com/channels/{header_message.guild.id}/{header_message.channel.id}/{header_message.id}"
        current_page = 1
        page_character_count = 0
        page_message_count = 0
        embed = Embed(title="Bulk Message Delete", color=0xFF0000,
                      timestamp=datetime.datetime.now(tz=datetime.timezone.utc))
        for message in sorted(cached_messages, key=lambda msg: msg.created_at):
            page_character_count += len(message.content[0:512]) + 3

            if page_character_count >= 5000 or page_message_count >= 25:
                embed.description = f"Messages {message_count}-{message_count + page_message_count} of [bulk delete]({link})"
                embed.set_footer(text=f"Page {current_page}")
                current_page += 1
                try:
                    await channel.send(embed=embed)
                except discord.HTTPException as e:
                    logger.debug(f"Bulk delete embed failed to send: {e}")
                embed: Embed = discord.Embed(title="Bulk Message Delete", color=0xFF0000,
                                             timestamp=datetime.datetime.now(tz=datetime.timezone.utc))
                page_character_count = len(message.content)
                message_count += page_message_count
                page_message_count = 0

            formatted_time = message.created_at.strftime("%b %d %Y %H:%M:%S")
            embed.add_field(name=f"{formatted_time}: {message.author}",
                            value="Message contained no content" if len(
                                message.content) == 0 else message.content if len(message.content) < 512
                            else f"{message.content[0:512]}...", inline=False)
            page_message_count += 1
            if current_page > 15:
                break
        message_count += page_message_count
        embed.description = f"Messages {message_count}-{message_count + page_message_count} of [bulk delete]({link})"
        embed.set_footer(text=f"Page {current_page}")
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as e:
            logger.debug(f"Bulk delete embed failed to send: {e}")
        header_embed.description = f"{len(message_ids)} Messages Deleted In: {message_channel.mention}\n" \
                                   f"Messages cached: {len(cached_messages)}/{len(message_ids)} \n" \
                                   f"Messages logged: {message_count}/{len(message_ids)}"
        await header_message.edit(embed=header_embed)

    @Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        """When a message is deleted and its not in the bot cache, log it anyway."""
        if payload.cached_message:
            return
        guild = self.bot.get_guild(int(payload.guild_id))
        message_channel = self.bot.get_channel(int(payload.channel_id))
        message_id = int(payload.message_id)
        message_created = discord.Object(message_id).created_at
        embed = Embed(title="Message Deleted",
                      description=f"Message Deleted In: {message_channel.mention}",
                      color=0xFF00F0, timestamp=message_created)
        embed.add_field(name="Message", value="N/A", inline=False)
        embed.set_footer(text=f"Message ID: {message_channel.id} - {message_id}\nSent at ")
        message_log_channel = await self.edit_delete_config.query_one(guild_id=guild.id)
        if message_log_channel is not None:
            channel = guild.get_channel(message_log_channel.messagelog_channel)
            if channel is not None:
                await channel.send(embed=embed)

    @Cog.listener('on_message_delete')
    async def on_message_delete(self, message: Message):
        """When a message is deleted, log it."""
        if message.author == self.bot.user:
            return
        audit: Optional[AuditLogEntry] = await self.check_audit(message.guild, discord.AuditLogAction.message_delete, message.created_at)
        embed: Embed = Embed(title="Message Deleted",
                             description=f"Message Deleted In: {message.channel.mention}\nSent by: {message.author.mention}",
                             color=0xFF0000, timestamp=message.created_at)
        embed.set_author(name=message.author, icon_url=message.author.avatar)
        if audit:
            if audit.target == message.author:
                audit_member = await message.guild.fetch_member(audit.user.id)
                embed.add_field(name="Message Deleted By: ", value=str(audit_member.mention), inline=False)
        if message.content:
            embed = await embed_paginatorinator("Message Content", embed, message.content)
        else:
            embed.add_field(name="Message Content:", value="N/A", inline=False)
        embed.set_footer(text=f"Message ID: {message.channel.id} - {message.id}\nUserID: {message.author.id}")
        if message.attachments:
            embed.add_field(name="Attachments", value=", ".join([i.proxy_url for i in message.attachments]))
        message_log_channel = await self.edit_delete_config.query_one(guild_id=message.guild.id)
        if message_log_channel is not None:
            channel = message.guild.get_channel(message_log_channel.messagelog_channel)
            if channel is not None:
                await channel.send(embed=embed)

    @Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        """Logs message edits that are not currently in the bots message cache"""
        if payload.cached_message:
            return
        mchannel = self.bot.get_channel(int(payload.channel_id))
        guild: Guild = mchannel.guild
        try:
            content: Optional[str] = payload.data['content']
        except KeyError:
            content = None
        author = payload.data.get("author")
        if not author:
            return
        guild_id: int = guild.id
        channel_id: int = payload.channel_id
        user_id: int = int(author['id'])
        if (self.bot.get_user(user_id)).bot:
            return  # Breakout if the user is a bot
        message_id: int = payload.message_id
        link: str = f"https://discordapp.com/channels/{guild_id}/{channel_id}/{message_id}"
        mention: str = f"<@!{user_id}>"
        avatar_link: str = f"https://cdn.discordapp.com/avatars/{user_id}/{author['avatar']}.webp?size=1024"
        embed: Embed = Embed(title="Message Edited",
                             description=f"[MESSAGE]({link}) From {mention}\nEdited In: {mchannel.mention}",
                             color=0xFFC400)
        embed.set_author(name=f"{author['username']}#{author['discriminator']}", icon_url=avatar_link)
        embed.add_field(name="Original", value="N/A", inline=False)
        if content:
            embed.add_field(name="Edited", value=content[0:1023], inline=False)
            if len(content) > 1024:
                embed.add_field(name="Edited Continued", value=content[1024:2000], inline=False)
        else:
            embed.add_field(name="Edited", value="N/A", inline=False)
        embed.set_footer(text=f"Message ID: {channel_id} - {message_id}\nUserID: {user_id}")
        message_log_channel = await self.edit_delete_config.query_one(guild_id=guild.id)
        if message_log_channel is not None:
            channel = guild.get_channel(message_log_channel.messagelog_channel)
            if channel is not None:
                await channel.send(embed=embed)

    @Cog.listener('on_message_edit')
    async def on_message_edit(self, before: Message, after: Message):
        """Logs message edits."""
        if before.author.bot:
            return
        if isinstance(before.channel, discord.DMChannel):
            return
        if after.edited_at is not None or before.edited_at is not None:
            # There is a reason for this. That reason is that otherwise, an infinite spam loop occurs
            guild_id = before.guild.id
            channel_id = before.channel.id
            user_id = before.author.id
            message_id = before.id
            link = f"https://discordapp.com/channels/{guild_id}/{channel_id}/{message_id}"
            embed: Embed = discord.Embed(title="Message Edited",
                                         description=f"[MESSAGE]({link}) From {before.author.mention}"
                                                     f"\nEdited In: {before.channel.mention}", color=0xFFC400,
                                         timestamp=after.edited_at)
            embed.set_author(name=before.author, icon_url=before.author.display_avatar)
            embed.set_footer(text=f"Message ID: {channel_id} - {message_id}\nUserID: {user_id}")
            if len(before.content) + len(after.content) < 5000:
                embed = await embed_paginatorinator("Original", embed, before.content)
                first_embed = await embed_paginatorinator("Edited", embed, after.content)
                second_embed = None
            else:
                first_embed = await embed_paginatorinator("Original", embed, before.content)
                embed.add_field(name="Original", value="Loading...", inline=False)
                second_embed = await embed_paginatorinator("Edited", embed, after.content)

            if after.attachments:
                first_embed.add_field(name="Attachments", value=", ".join([i.url for i in before.attachments]))
            message_log_channel = await self.edit_delete_config.query_one(guild_id=before.guild.id)
            if message_log_channel is not None:
                channel = before.guild.get_channel(message_log_channel.messagelog_channel)
                if channel is not None:
                    first_message = await channel.send(embed=first_embed)
                    if second_embed:
                        second_message = await channel.send(embed=second_embed)
                        first_embed.add_field(name="Edited",
                                              value=f"[CONTINUED](https://discordapp.com/channels/{guild_id}"
                                                    f"/{second_message.channel.id}/{second_message.id})", inline=False)
                        await first_message.edit(embed=first_embed)
                        embed.set_field_at(0, name="Original",
                                           value=f"[CONTINUED](https://discordapp.com/channels/{guild_id}"
                                                 f"/{first_message.channel.id}/{first_message.id})", inline=False)
                        await second_message.edit(embed=second_embed)

    @Cog.listener('on_member_ban')
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        """Logs raw member ban events, even if not banned via &ban"""
        audit: Optional[AuditLogEntry] = await self.check_audit(guild, discord.AuditLogAction.ban)
        embed: Embed = Embed(title="User Banned", color=0xff6700)
        embed.set_thumbnail(url=user.avatar)
        embed.add_field(name="Banned user", value=f"{user}|({user.id})")
        if audit and audit.target == user:
            acton_member: Member = await guild.fetch_member(audit.user.id)
            embed.description = f"User banned by: {acton_member.mention}\n{acton_member}|({acton_member.id})"
            embed.add_field(name="Reason", value=audit.reason, inline=False)
            embed.set_footer(text=f"Actor ID: {acton_member.id}\nTarget ID: {user.id}")
        else:
            embed.description = "No audit log entry found"
            embed.set_footer(text=f"Actor ID: Unknown\nTarget ID: {user.id}")

        message_log_channel = await self.edit_delete_config.query_one(guild_id=guild.id)
        if message_log_channel is not None:
            channel = guild.get_channel(message_log_channel.messagelog_channel)
            if channel is not None:
                await channel.send(embed=embed)

    @command()
    @has_permissions(administrator=True)
    async def messagelogconfig(self, ctx: DozerContext, channel_mentions: discord.TextChannel):
        """Set the modlog channel for a server by passing the channel id"""
        results: List[GuildMessageLog] = await GuildMessageLog.get_by(guild_id=ctx.guild.id)
        config: GuildMessageLog
        if len(results) != 0:
            config = results[0]
            config.name = ctx.guild.name
            config.messagelog_channel = channel_mentions.id
        else:
            config = GuildMessageLog(guild_id=ctx.guild.id, messagelog_channel=channel_mentions.id, name=ctx.guild.name)
        await config.update_or_add()
        self.edit_delete_config.invalidate_entry(guild_id=ctx.guild.id)
        await ctx.send(ctx.message.author.mention + ', messagelog settings configured!')

    messagelogconfig.example_usage = """
        `{prefix}messagelogconfig #orwellian-dystopia` - set a channel named #orwellian-dystopia to log message edits/deletions
        """

    @group(invoke_without_command=True)
    @has_permissions(administrator=True)
    async def memberlogconfig(self, ctx: DozerContext):
        """Command group to configure Join/Leave logs"""
        config: List[CustomJoinLeaveMessages] = await CustomJoinLeaveMessages.get_by(guild_id=ctx.guild.id)
        if len(config):
            embed: Embed = Embed(title=f"Join/Leave configuration for {ctx.guild}", color=blurple)
            channel = ctx.guild.get_channel(config[0].channel_id)
            embed.add_field(name="Message Channel", value=channel.mention if channel else "None")
            embed.add_field(name="Ping on join", value=config[0].ping)
            embed.add_field(name="Send on verify", value=config[0].send_on_verify)
            embed.add_field(name="Join template", value=config[0].join_message, inline=False)
            embed.add_field(name="Join Example", value=format_join_leave(config[0].join_message, ctx.author))
            embed.add_field(name="Leave template", value=config[0].leave_message, inline=False)
            embed.add_field(name="Leave Example", value=format_join_leave(config[0].leave_message, ctx.author))
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
    @has_permissions(administrator=True)
    async def viewconfig(self, ctx: DozerContext):
        """Command to view Join/Leave logs configuration."""
        await self.memberlogconfig(ctx)

    @memberlogconfig.command()
    @has_permissions(manage_guild=True)
    async def setchannel(self, ctx: DozerContext, channel: discord.TextChannel):
        """Configure join/leave channel"""
        config: CustomJoinLeaveMessages = CustomJoinLeaveMessages(
            guild_id=ctx.guild.id,
            channel_id=channel.id
        )
        await config.update_or_add()
        e: Embed = Embed(color=blurple)
        e.add_field(name='Success!', value=f"Join/Leave log channel has been set to {channel.mention}")
        e.set_footer(text='Triggered by ' + escape_markdown(ctx.author.display_name))
        await ctx.send(embed=e)

    @memberlogconfig.command()
    @has_permissions(manage_guild=True)
    async def toggleping(self, ctx: DozerContext):
        """Toggles whenever a new member gets pinged on join"""
        config: List[CustomJoinLeaveMessages] = await CustomJoinLeaveMessages.get_by(guild_id=ctx.guild.id)
        if len(config):
            config[0].ping = not config[0].ping
        else:
            config = [CustomJoinLeaveMessages(guild_id=ctx.guild.id, ping=True)]
        await config[0].update_or_add()

        e: Embed = Embed(color=blurple)
        e.add_field(name='Success!', value=f"Ping on join is set to: {config[0].ping}")
        e.set_footer(text='Triggered by ' + escape_markdown(ctx.author.display_name))
        await ctx.send(embed=e)

    @memberlogconfig.command()
    @has_permissions(manage_guild=True)
    async def togglesendonverify(self, ctx: DozerContext):
        """Toggles if a join log is sent on user joining or on completing verification"""
        config: List[CustomJoinLeaveMessages] = await CustomJoinLeaveMessages.get_by(guild_id=ctx.guild.id)
        if len(config):
            config[0].send_on_verify = not config[0].send_on_verify
        else:
            config = [CustomJoinLeaveMessages(guild_id=ctx.guild.id, send_on_verify=True)]
        await config[0].update_or_add()

        e: Embed = Embed(color=blurple)
        e.add_field(name='Success!', value=f"Send on verify is set to: {config[0].send_on_verify}")
        e.set_footer(text='Triggered by ' + ctx.author.display_name)
        await ctx.send(embed=e)

    @memberlogconfig.command()
    @has_permissions(manage_guild=True)
    async def setjoinmessage(self, ctx: DozerContext, *, template: Optional[str] = None):
        """Configure custom join message template"""
        e: Embed = Embed(color=blurple)
        e.set_footer(text='Triggered by ' + escape_markdown(ctx.author.display_name))
        config: CustomJoinLeaveMessages
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
    async def setleavemessage(self, ctx: DozerContext, *, template: Optional[str] = None):
        """Configure custom leave message template"""
        e: Embed = Embed(color=blurple)
        e.set_footer(text='Triggered by ' + escape_markdown(ctx.author.display_name))
        config: CustomJoinLeaveMessages
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
    async def disable(self, ctx: DozerContext):
        """Disables Join/Leave logging"""
        e: Embed = Embed(color=blurple)
        e.set_footer(text='Triggered by ' + escape_markdown(ctx.author.display_name))
        config: CustomJoinLeaveMessages = CustomJoinLeaveMessages(
            guild_id=ctx.guild.id,
            channel_id=CustomJoinLeaveMessages.nullify
        )
        await config.update_or_add()
        e.add_field(name='Success!', value="Join/Leave logs have been disabled")
        await ctx.send(embed=e)

    @memberlogconfig.command()
    @has_permissions(manage_guild=True)
    async def help(self, ctx: DozerContext):
        # I cannot put formatting example in example_usage because then it tries to format the example
        """Displays message formatting key"""
        e: Embed = Embed(color=blurple)
        e.set_footer(text='Triggered by ' + escape_markdown(ctx.author.display_name))
        e.description = """
        `{guild}` = guild name
        `{user}` = user's name plus discriminator ex. SnowPlow#5196
        `{user_name}` = user's name without discriminator
        `{user_mention}` = user's mention
        `{user_id}` = user's ID
        """
        await ctx.send(embed=e)

    @command()
    @has_permissions(manage_nicknames=True)
    @bot_has_permissions(manage_nicknames=True)
    async def locknickname(self, ctx: DozerContext, member: Member, *, name: str):
        """Locks a members nickname to a particular string, in essence revoking nickname change perms"""
        try:
            await member.edit(nick=name)
        except discord.Forbidden:
            raise BadArgument(f"Dozer is not elevated high enough to change {member}'s nickname")
        lock: NicknameLock = NicknameLock(
            guild_id=ctx.guild.id,
            member_id=member.id,
            locked_name=name,
            timeout=time.time()
        )
        await lock.update_or_add()
        e: Embed = Embed(color=blurple)
        e.add_field(name='Success!', value=f"**{member}**'s nickname has been locked to **{name}**")
        e.set_footer(text='Triggered by ' + escape_markdown(ctx.author.display_name))
        await ctx.send(embed=e)

    locknickname.example_usage = """
    `{prefix}locknickname @Snowplow#5196 Dozer`: Locks user snowplows nickname to "dozer"
    """

    @command()
    @has_permissions(manage_nicknames=True)
    @bot_has_permissions(manage_nicknames=True)
    async def unlocknickname(self, ctx: DozerContext, member: Member):
        """Removes nickname lock from member"""
        deleted = await NicknameLock.delete(guild_id=ctx.guild.id, member_id=member.id)
        if int(deleted.split(" ", 1)[1]):
            e: Embed = Embed(color=blurple)
            e.add_field(name='Success!', value=f"Nickname lock for {member} has been removed")
            e.set_footer(text='Triggered by ' + escape_markdown(ctx.author.display_name))
            await ctx.send(embed=e)
        else:
            raise BadArgument(f"No member of {member} found with nickname lock!")

    unlocknickname.example_usage = """
    `{prefix}unlocknickname @Snowplow#5196`: Removes nickname lock from user dozer
    """


class NicknameLock(db.DatabaseTable):
    """Holds nickname lock info"""
    __tablename__ = "nickname_locks"
    __uniques__ = "guild_id, member_id"

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint NOT NULL,
            member_id bigint NOT NULL,
            locked_name text,
            timeout bigint,
            UNIQUE (guild_id, member_id)
            )""")

    def __init__(self, guild_id: int, member_id: int, locked_name: Optional[str], timeout: Optional[float] = None):
        super().__init__()
        self.guild_id: int = guild_id
        self.member_id: int = member_id
        self.locked_name: Optional[str] = locked_name
        self.timeout: Optional[float] = timeout

    @classmethod
    async def get_by(cls, **kwargs) -> List["NicknameLock"]:
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = NicknameLock(guild_id=result.get("guild_id"), member_id=result.get("member_id"),
                               locked_name=result.get("locked_name"), timeout=result.get("timeout"))
            result_list.append(obj)
        return result_list


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

    def __init__(self, guild_id: int, name: str, messagelog_channel: int):
        super().__init__()
        self.guild_id: int = guild_id
        self.name: str = name
        self.messagelog_channel: int = messagelog_channel

    @classmethod
    async def get_by(cls, **kwargs) -> List["GuildMessageLog"]:
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = GuildMessageLog(guild_id=result.get("guild_id"), name=result.get("name"),
                                  messagelog_channel=result.get("messagelog_channel"))
            result_list.append(obj)
        return result_list


async def send_log(member: Member):
    """Sends the message for when a user joins or leave a guild"""
    config = await CustomJoinLeaveMessages.get_by(guild_id=member.guild.id)
    if len(config):
        channel = member.guild.get_channel(config[0].channel_id)
        if channel:
            embed: Embed = Embed(color=0x00FF00)
            embed.set_author(name='Member Joined', icon_url=member.avatar.replace(format='png', size=32))
            embed.description = format_join_leave(config[0].join_message, member)
            embed.set_footer(text="{} | {} members".format(member.guild.name, member.guild.member_count))
            try:
                await channel.send(content=member.mention if config[0].ping else None, embed=embed)
            except discord.Forbidden:
                logger.warning(
                    f"Guild {member.guild}({member.guild.id}) has invalid permissions for join/leave logs")


def format_join_leave(template: str, member: Member):
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
        return "{user_mention}\n{user} ({user_id})".format(user=str(member), user_mention=member.mention,
                                                           user_id=member.id)


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
            name varchar NOT NULL,
            send_on_verify boolean
            )""")

    def __init__(self, guild_id: int, channel_id: int = None, ping: Optional[bool] = None, join_message: Optional[str] = None,
                 leave_message: Optional[str] = None, send_on_verify: Optional[bool] = False):
        super().__init__()
        self.guild_id: int = guild_id
        self.channel_id: Optional[int] = channel_id
        self.ping: Optional[bool] = ping
        self.join_message: Optional[str] = join_message
        self.leave_message: Optional[str] = leave_message
        self.send_on_verify: Optional[bool] = send_on_verify

    @classmethod
    async def get_by(cls, **kwargs) -> List["CustomJoinLeaveMessages"]:
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = CustomJoinLeaveMessages(guild_id=result.get("guild_id"), channel_id=result.get("channel_id"),
                                          ping=result.get("ping"),
                                          join_message=result.get("join_message"),
                                          leave_message=result.get("leave_message"),
                                          send_on_verify=result.get("send_on_verify"))
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

    async def version_2(self):
        """Updates database stuff to version 2"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"alter table {self.__tablename__} "
                               f"add if not exists send_on_verify boolean default null;")

    __versions__ = [version_1, version_2]


class GuildNewMember(db.DatabaseTable):
    """Holds new member info"""
    __tablename__ = 'new_members'
    __uniques__ = 'guild_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY,
            channel_id bigint NOT NULL,
            role_id bigint NOT NULL,
            message varchar NOT NULL
            )""")

    def __init__(self, guild_id: int, channel_id: int, role_id: int, message: str, require_team: bool):
        super().__init__()
        self.guild_id: int = guild_id
        self.channel_id: int = channel_id
        self.role_id: int = role_id
        self.message: str = message
        self.require_team: bool = require_team

    @classmethod
    async def get_by(cls, **kwargs) -> List["GuildNewMember"]:
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = GuildNewMember(guild_id=result.get("guild_id"), channel_id=result.get("channel_id"),
                                 role_id=result.get("role_id"), message=result.get("message"),
                                 require_team=result.get("require_team"))
            result_list.append(obj)
        return result_list

    async def version_1(self):
        """DB migration v1"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            ALTER TABLE {self.__tablename__} ADD require_team bool NOT NULL DEFAULT false;
            """)

    __versions__ = [version_1]


async def setup(bot: "Dozer"):
    """Adds the actionlog cog to the bot."""
    await bot.add_cog(Actionlog(bot))
