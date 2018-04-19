import asyncio
import discord
import re

from discord.ext.commands import BadArgument, has_permissions, bot_has_permissions, RoleConverter

from ._utils import *
from .. import db
from ..utils import clean


class SafeRoleConverter(RoleConverter):
    async def convert(self, ctx, arg):
        try:
            return await super().convert(ctx, arg)
        except BadArgument:
            if arg.casefold() in (
            'everyone', '@everyone', '@/everyone', '@.everyone', '@ everyone', '@\N{ZERO WIDTH SPACE}everyone'):
                return ctx.guild.default_role
            else:
                raise


class Moderation(Cog):
    """A cog to handle moderation tasks."""

    """=== Helper functions ==="""

    async def mod_log(self, member : discord.Member, action : str, target : discord.User, reason, orig_channel=None, embed_color=discord.Color.red()):
        #modlog_message = "{} has {} {} because {}".format(ctx.author, action, target, reason)
        modlog_embed = discord.Embed(
            color = embed_color,
            title = f"User {action}!"

        )
        modlog_embed.add_field(name=f"{action.capitalize()} user", value=f"{target.mention} ({target} | {target.id})", inline=False)
        modlog_embed.add_field(name="Requested by", value=f"{member.mention} ({member} | {member.id})", inline=False)
        modlog_embed.add_field(name="Reason", value=reason, inline=False)

        # modlog_message = "{} has {} {} because {}".format(member, action, target, reason)
        # modlog_message = clean(ctx=ctx, text=modlog_message)

        with db.Session() as session:
            modlog_channel = session.query(GuildModLog).filter_by(id=member.guild.id).one_or_none()
            if orig_channel is not None:
                await orig_channel.send(embed=modlog_embed)
            if modlog_channel is not None:
                channel = member.guild.get_channel(modlog_channel.modlog_channel)
                if channel is not None:
                    await channel.send(embed=modlog_embed)
            else:
                if orig_channel is not None:
                    await orig_channel.send("Please configure modlog channel to enable modlog functionality")

    async def perm_override(self, member, **overwrites):
        coros = []
        for channel in member.guild.channels:
            overwrite = channel.overwrites_for(member)
            can_perm_override = channel.permissions_for(member.guild.me).manage_roles
            if can_perm_override:
                overwrite.update(**overwrites)
                coros.append(
                    channel.set_permissions(target=member, overwrite=None if overwrite.is_empty() else overwrite))
        await asyncio.gather(*coros)

    async def punishment_timer(self, ctx, timing, target, punishment, reason):
        regex_string = re.compile(r"((?P<hours>\d+)h)?((?P<minutes>\d+)m)?")
        matches = re.match(regex_string, timing).groupdict()
        try:
            hours = int(matches.get('hours'))
        except:
            hours = 0
        try:
            minutes = int(matches.get('minutes'))
        except:
            minutes = 0
        time = (hours * 3600) + (minutes * 60)
        if time == 0:
            await self.mod_log(member=ctx.author, action=punishment.past_participle, target=target, reason=reason, orig_channel=ctx.channel)
        else:
            reasoning = re.sub(pattern=regex_string, string=reason, repl="").lstrip("  ")
            await self.mod_log(member=ctx.author, action=punishment.past_participle, target=target, reason=reasoning, orig_channel=ctx.channel)

            await asyncio.sleep(time)
            with db.Session() as session:
                user = session.query(punishment).filter_by(id=target.id).one_or_none()
                if user is not None:
                    if punishment == Deafen:
                        self.bot.loop.create_task(
                            coro=self.undeafen.callback(self=self, ctx=ctx, member_mentions=target))
                    if punishment == Mute:
                        self.bot.loop.create_task(coro=self.unmute.callback(self=self, ctx=ctx, member_mentions=target))

    async def _check_links_warn(self, msg, role):
        warn_msg = await msg.channel.send(f"{msg.author.mention}, you need the `{role.name}` role to post links!")
        await asyncio.sleep(3)
        await warn_msg.delete()

    async def check_links(self, msg):
        if msg.guild is None or not msg.guild.me.guild_permissions.manage_messages:
            return
        with db.Session() as session:
            config = session.query(GuildMessageLinks).filter_by(guild_id=msg.guild.id).one_or_none()
            if config is None:
                return
            role = discord.utils.get(msg.guild.roles, id=config.role_id)
            if role is None:
                return
            if role not in msg.author.roles and re.search("https?://", msg.content):
                await msg.delete()
                self.bot.loop.create_task(coro=self._check_links_warn(msg, role))
                return True
        return False

    """=== Event handlers ==="""

    async def on_member_join(self, member):
        join = discord.Embed(type='rich', color=0x00FF00)
        join.set_author(name='Member Joined', icon_url=member.avatar_url_as(format='png', size=32))
        join.description = "{0.mention}\n{0} ({0.id})".format(member)
        join.set_footer(text="{} | {} members".format(member.guild.name, member.guild.member_count))
        with db.Session() as session:
            memberlogchannel = session.query(GuildMemberLog).filter_by(id=member.guild.id).one_or_none()
            if memberlogchannel is not None:
                channel = member.guild.get_channel(memberlogchannel.memberlog_channel)
                await channel.send(embed=join)
            user = session.query(Mute).filter_by(id=member.id, guild=member.guild.id).one_or_none()
            if user is not None:
                await self.perm_override(member, add_reactions=False, send_messages=False)
            user = session.query(Deafen).filter_by(id=member.id, guild=member.guild.id).one_or_none()
            if user is not None:
                await self.perm_override(member, read_messages=False)

    async def on_member_remove(self, member):
        leave = discord.Embed(type='rich', color=0xFF0000)
        leave.set_author(name='Member Left', icon_url=member.avatar_url_as(format='png', size=32))
        leave.description = "{0.mention}\n{0} ({0.id})".format(member)
        leave.set_footer(text="{} | {} members".format(member.guild.name, member.guild.member_count))
        with db.Session() as session:
            memberlogchannel = session.query(GuildMemberLog).filter_by(id=member.guild.id).one_or_none()
            if memberlogchannel is not None:
                channel = member.guild.get_channel(memberlogchannel.memberlog_channel)
                await channel.send(embed=leave)

    async def on_message(self, message):
        if message.author.bot or message.guild is None or not message.guild.me.guild_permissions.manage_roles:
            return

        if await self.check_links(message):
            return
        with db.Session() as session:
            config = session.query(GuildNewMember).filter_by(guild_id=message.guild.id).one_or_none()
            if config is not None:
                string = config.message
                content = message.content.casefold()
                if string not in content: return
                channel = config.channel_id
                role_id = config.role_id
                if message.channel.id != channel: return
                await message.author.add_roles(discord.utils.get(message.guild.roles, id=role_id))


    async def on_message_delete(self, message):
        e = discord.Embed(type='rich')
        e.title = 'Message Deletion'
        e.color = 0xFF0000
        e.add_field(name='Author', value=message.author)
        e.add_field(name='Author pingable', value=message.author.mention)
        e.add_field(name='Channel', value=message.channel)
        if 1024 > len(message.content) > 0:
            e.add_field(name="Deleted message", value=message.content)
        elif len(message.content) != 0:
            e.add_field(name="Deleted message", value=message.content[0:1023])
            e.add_field(name="Deleted message continued", value=message.content[1024:2000])
        elif len(message.content) == 0:
            for i in message.embeds:
                e.add_field(name="Title", value=i.title)
                e.add_field(name="Description", value=i.description)
                e.add_field(name="Timestamp", value=i.timestamp)
                for x in i.fields:
                    e.add_field(name=x.name, value=x.value)
                e.add_field(name="Footer", value=i.footer)
        if message.attachments:
            e.add_field(name="Attachments", value=", ".join([i.url for i in message.attachments]))
        with db.Session() as session:
            messagelogchannel = session.query(GuildMessageLog).filter_by(id=message.guild.id).one_or_none()
            if messagelogchannel is not None:
                channel = message.guild.get_channel(messagelogchannel.messagelog_channel)
                if channel is not None:
                    await channel.send(embed=e)

    async def on_message_edit(self, before, after):
        await self.check_links(after)
        if before.author.bot: return
        if after.edited_at is not None or before.edited_at is not None:
            # There is a reason for this. That reason is that otherwise, an infinite spam loop occurs
            e = discord.Embed(type='rich')
            e.title = 'Message Edited'
            e.color = 0xFF0000
            e.add_field(name='Author', value=before.author)
            e.add_field(name='Author pingable', value=before.author.mention)
            e.add_field(name='Channel', value=before.channel)
            if 1024 > len(before.content) > 0:
                e.add_field(name="Old message", value=before.content)
            elif len(before.content) != 0:
                e.add_field(name="Old message", value=before.content[0:1023])
                e.add_field(name="Old message continued", value=before.content[1024:2000])
            elif len(before.content) == 0 and before.edited_at is not None:
                for i in before.embeds:
                    e.add_field(name="Title", value=i.title)
                    e.add_field(name="Description", value=i.description)
                    e.add_field(name="Timestamp", value=i.timestamp)
                    for x in i.fields:
                        e.add_field(name=x.name, value=x.value)
                    e.add_field(name="Footer", value=i.footer)
            if before.attachments:
                e.add_field(name="Attachments", value=", ".join([i.url for i in before.attachments]))
            if 0 < len(after.content) < 1024:
                e.add_field(name="New message", value=after.content)
            elif len(after.content) != 0:
                e.add_field(name="New message", value=after.content[0:1023])
                e.add_field(name="New message continued", value=after.content[1024:2000])
            elif len(after.content) == 0 and after.edited_at is not None:
                for i in after.embeds:
                    e.add_field(name="Title", value=i.title)
                    e.add_field(name="Description", value=i.description)
                    e.add_field(name="Timestamp", value=i.timestamp)
                    for x in i.fields:
                        e.add_field(name=x.name, value=x.value)
            if after.attachments:
                e.add_field(name="Attachments", value=", ".join([i.url for i in before.attachments]))
            with db.Session() as session:
                messagelogchannel = session.query(GuildMessageLog).filter_by(id=before.guild.id).one_or_none()
                if messagelogchannel is not None:
                    channel = before.guild.get_channel(messagelogchannel.messagelog_channel)
                    if channel is not None:
                        await channel.send(embed=e)

    """=== Direct moderation commands ==="""

    @command()
    @has_permissions(manage_roles=True)
    @bot_has_permissions(manage_roles=True)
    async def timeout(self, ctx, duration: float):
        """Set a timeout (no sending messages or adding reactions) on the current channel."""
        with db.Session() as session:
            settings = session.query(MemberRole).filter_by(id=ctx.guild.id).one_or_none()
            if settings is None:
                settings = MemberRole(id=ctx.guild.id)
                session.add(settings)

            member_role = discord.utils.get(ctx.guild.roles,
                                            id=settings.member_role)  # None-safe - nonexistent or non-configured role return None

        if member_role is not None:
            targets = {member_role}
        else:
            await ctx.send(
                '{0.author.mention}, the members role has not been configured. This may not work as expected. Use `{0.prefix}help memberconfig` to see how to set this up.'.format(
                    ctx))
            targets = set(sorted(ctx.guild.roles)[:ctx.author.top_role.position])

        to_restore = [(target, ctx.channel.overwrites_for(target)) for target in targets]
        for target, overwrite in to_restore:
            new_overwrite = discord.PermissionOverwrite.from_pair(*overwrite.pair())
            new_overwrite.update(send_messages=False, add_reactions=False)
            await ctx.channel.set_permissions(target, overwrite=new_overwrite)

        for allow_target in (ctx.me, ctx.author):
            overwrite = ctx.channel.overwrites_for(allow_target)
            new_overwrite = discord.PermissionOverwrite.from_pair(*overwrite.pair())
            new_overwrite.update(send_messages=True)
            await ctx.channel.set_permissions(allow_target, overwrite=new_overwrite)
            to_restore.append((allow_target, overwrite))

        e = discord.Embed(title='Timeout - {}s'.format(duration), description='This channel has been timed out.',
                          color=discord.Color.blue())
        e.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url_as(format='png', size=32))
        msg = await ctx.send(embed=e)

        await asyncio.sleep(duration)

        for target, overwrite in to_restore:
            if all(permission is None for _, permission in overwrite):
                await ctx.channel.set_permissions(target, overwrite=None)
            else:
                await ctx.channel.set_permissions(target, overwrite=overwrite)

        e.description = 'The timeout has ended.'
        await msg.edit(embed=e)
    timeout.example_usage = """
    `{prefix}timeout 60` - prevents sending messages in this channel for 1 minute (60s)
    """

    @command(aliases=["purge"])
    @has_permissions(manage_messages=True)
    @bot_has_permissions(manage_messages=True, read_message_history=True)
    async def prune(self, ctx, num_to_delete: int):
        """Bulk delete a set number of messages from the current channel."""
        await ctx.message.channel.purge(limit=num_to_delete + 1)
        await ctx.send(
            "Deleted {n} messages under request of {user}".format(n=num_to_delete, user=ctx.message.author.mention),
            delete_after=5)
    prune.example_usage = """
    `{prefix}prune 10` - Delete the last 10 messages in the current channel.
    """

    @command()
    @has_permissions(ban_members=True)
    @bot_has_permissions(ban_members=True)
    async def ban(self, ctx, user_mention: discord.User, *, reason="No reason provided"):
        """Bans the user mentioned."""
        await ctx.guild.ban(user_mention, reason=reason)
        await self.mod_log(member=ctx.author, action="banned", target=user_mention, reason=reason, orig_channel=ctx.channel)
    ban.example_usage = """
    `{prefix}ban @user reason - ban @user for a given (optional) reason
    """

    @command()
    @has_permissions(ban_members=True)
    @bot_has_permissions(ban_members=True)
    async def unban(self, ctx, user_mention: discord.User, *, reason="No reason provided"):
        """Unbans the user mentioned."""
        await ctx.guild.unban(user_mention, reason=reason)
        await self.mod_log(member=ctx.author, action="banned", target=user_mention, reason=reason, orig_channel=ctx.channel)
    unban.example_usage = """
    `{prefix}unban user_id reason - unban the user corresponding to the ID for a given (optional) reason
    """

    @command()
    @has_permissions(kick_members=True)
    @bot_has_permissions(kick_members=True)
    async def kick(self, ctx, user_mention: discord.User, *, reason="No reason provided"):
        """Kicks the user mentioned."""
        await ctx.guild.kick(user_mention, reason=reason)
        await self.mod_log(member=ctx.author, action="kicked", target=user_mention, reason=reason, orig_channel=ctx.channel)
    kick.example_usage = """
    `{prefix}kick @user reason - kick @user for a given (optional) reason
    """

    @command()
    @has_permissions(kick_members=True)
    @bot_has_permissions(manage_roles=True)
    async def mute(self, ctx, member_mentions: discord.Member, *, reason="No reason provided"):
        """Mute a user to prevent them from sending messages"""
        async with ctx.typing(), db.Session() as session:
            user = session.query(Mute).filter_by(id=member_mentions.id, guild=ctx.guild.id).one_or_none()
            if user is not None:
                await ctx.send("User is already muted!")
            else:
                user = Mute(id=member_mentions.id, guild=ctx.guild.id)
                session.add(user)
                await self.perm_override(member_mentions, send_messages=False, add_reactions=False)
                self.bot.loop.create_task(
                    self.punishment_timer(ctx, reason, member_mentions, punishment=Mute, reason=reason))
    mute.example_usage = """
    `{prefix}mute @user 1h reason` - mute @user for 1 hour for a given reason, the timing component (1h) and reason is optional.
    """

    @command()
    @has_permissions(kick_members=True)
    @bot_has_permissions(manage_roles=True)
    async def unmute(self, ctx, member_mentions: discord.Member, reason="No reason provided"):
        """Unmute a user to allow them to send messages again."""
        async with ctx.typing(), db.Session() as session:
            user = session.query(Mute).filter_by(id=member_mentions.id, guild=ctx.guild.id).one_or_none()
            if user is not None:
                session.delete(user)
                await self.perm_override(member_mentions, send_messages=None, add_reactions=None)
                await self.mod_log(member=ctx.author, action="unmuted", target=member_mentions, reason=reason,
                                   orig_channel=ctx.channel, embed_color=discord.Color.green())
            else:
                await ctx.send("User is not muted!")
    unmute.example_usage = """
    `{prefix}unmute @user reason - unmute @user for a given (optional) reason
    """

    @command()
    @has_permissions(kick_members=True)
    @bot_has_permissions(manage_roles=True)
    async def deafen(self, ctx, member_mentions: discord.Member, *, reason="No reason provided"):
        """Deafen a user to prevent them from both sending messages but also reading messages."""
        async with ctx.typing(), db.Session() as session:
            user = session.query(Deafen).filter_by(id=member_mentions.id, guild=ctx.guild.id).one_or_none()
            if user is not None:
                await ctx.send("User is already deafened!")
            else:
                user = Deafen(id=member_mentions.id, guild=ctx.guild.id, self_inflicted=False)
                session.add(user)
                await self.perm_override(member_mentions, read_messages=False)
                self.bot.loop.create_task(
                    self.punishment_timer(ctx, reason, member_mentions, punishment=Deafen, reason=reason))

    deafen.example_usage = """
    `{prefix}deafen @user 1h reason` - deafen @user for 1 hour for a given reason, the timing component (1h) is optional.
    """

    @command()
    @bot_has_permissions(manage_roles=True)
    async def selfdeafen(self, ctx, timing, *, reason="No reason provided"):
        """Deafen yourself for a given time period to prevent you from reading or sending messages; useful as a study tool."""
        async with ctx.typing(), db.Session() as session:
            user = session.query(Deafen).filter_by(id=ctx.author.id, guild=ctx.guild.id).one_or_none()
            if user is not None:
                await ctx.send("You are already deafened!")
            else:
                user = Deafen(id=ctx.author.id, guild=ctx.guild.id, self_inflicted=True)
                session.add(user)
                await self.perm_override(member=ctx.author, read_messages=False)
                self.bot.loop.create_task(self.punishment_timer(ctx, timing, ctx.author, punishment=Deafen, reason=reason))

    selfdeafen.example_usage = """
    `{prefix}selfdeafen time (1h5m, both optional) reason`: deafens you if you need to get work done
    """

    @command()
    @has_permissions(kick_members=True)
    @bot_has_permissions(manage_roles=True)
    async def undeafen(self, ctx, member_mentions: discord.Member, reason="No reason provided"):
        """Undeafen a user to allow them to see message and send message again."""
        async with ctx.typing(), db.Session() as session:
            user = session.query(Deafen).filter_by(id=member_mentions.id, guild=ctx.guild.id).one_or_none()
            if user is not None:
                await self.perm_override(member=member_mentions, read_messages=None)
                session.delete(user)
                if user.self_inflicted:
                    reason = "Self-deafen timer expired"
                await self.mod_log(member=ctx.author, action="undeafened", target=member_mentions, reason=reason,
                                   orig_channel=ctx.channel, embed_color=discord.Color.green())
            else:
                await ctx.send("User is not deafened!")
    undeafen.example_usage = """
    `{prefix}undeafen @user reason - undeafen @user for a given (optional) reason
    """

    """=== Configuration commands ==="""

    @command()
    @has_permissions(administrator=True)
    async def modlogconfig(self, ctx, channel_mentions: discord.TextChannel):
        """Set the modlog channel for a server by passing the channel id"""
        with db.Session() as session:
            config = session.query(GuildModLog).filter_by(id=str(ctx.guild.id)).one_or_none()
            if config is not None:
                config.name = ctx.guild.name
                config.modlog_channel = str(channel_mentions.id)
            else:
                config = GuildModLog(id=ctx.guild.id, modlog_channel=channel_mentions.id, name=ctx.guild.name)
                session.add(config)
            await ctx.send(ctx.message.author.mention + ', modlog settings configured!')
    modlogconfig.example_usage = """
    `{prefix}modlogconfig #join-leave-logs` - set a channel named #join-leave-logs to log joins/leaves 
    """

    @command()
    @has_permissions(administrator=True)
    async def nmconfig(self, ctx, channel_mention: discord.TextChannel, role: discord.Role, *, message):
        """Sets the config for the new members channel"""
        with db.Session() as session:
            config = session.query(GuildNewMember).filter_by(guild_id=ctx.guild.id).one_or_none()
            if config is not None:
                config.channel_id = channel_mention.id
                config.role_id = role.id
                config.message = message.casefold()
            else:
                config = GuildNewMember(guild_id=ctx.guild.id, channel_id=channel_mention.id, role_id=role.id,
                                        message=message.casefold())
                session.add(config)

        role_name = role.name
        await ctx.send(
            "New Member Channel configured as: {channel}. Role configured as: {role}. Message: {message}".format(
                channel=channel_mention.name, role=role_name, message=message))
    nmconfig.example_usage = """
    `{prefix}nmconfig #new_members Member I have read the rules and regulations` - Configures the #new_members channel so if someone types "I have read the rules and regulations" it assigns them the Member role. 
    """

    @command()
    @has_permissions(administrator=True)
    async def memberconfig(self, ctx, *, member_role: SafeRoleConverter):
        """
        Set the member role for the guild.
        The member role is the role used for the timeout command. It should be a role that all members of the server have.
        """
        if member_role >= ctx.author.top_role:
            raise BadArgument('member role cannot be higher than your top role!')

        with db.Session() as session:
            settings = session.query(MemberRole).filter_by(id=ctx.guild.id).one_or_none()
            if settings is None:
                settings = MemberRole(id=ctx.guild.id, member_role=member_role.id)
                session.add(settings)
            else:
                settings.member_role = member_role.id
        await ctx.send('Member role set as `{}`.'.format(member_role.name))
    memberconfig.example_usage = """
    `{prefix}memberconfig Members` - set a role called "Members" as the member role
    `{prefix}memberconfig @everyone` - set the default role as the member role
    `{prefix}memberconfig everyone` - set the default role as the member role (ping-safe)
    `{prefix}memberconfig @ everyone` - set the default role as the member role (ping-safe)
    `{prefix}memberconfig @.everyone` - set the default role as the member role (ping-safe)
    `{prefix}memberconfig @/everyone` - set the default role as the member role (ping-safe)
    """

    @command()
    @has_permissions(administrator=True)
    @bot_has_permissions(manage_messages=True)
    async def linkscrubconfig(self, ctx, *, link_role: SafeRoleConverter):
        """
        Set a role that users must have in order to post links.
        This accepts the safe default role conventions that the memberconfig command does.
        """
        if link_role >= ctx.author.top_role:
            raise BadArgument('Link role cannot be higher than your top role!')

        with db.Session() as session:
            settings = session.query(GuildMessageLinks).filter_by(guild_id=ctx.guild.id).one_or_none()
            if settings is None:
                settings = GuildMessageLinks(guild_id=ctx.guild.id, role_id=link_role.id)
                session.add(settings)
            else:
                settings.role_id = link_role.id
        await ctx.send(f'Link role set as `{link_role.name}`.')
    linkscrubconfig.example_usage = """
    `{prefix}linkscrubconfig Links` - set a role called "Links" as the link role
    `{prefix}linkscrubconfig @everyone` - set the default role as the link role
    `{prefix}linkscrubconfig everyone` - set the default role as the link role (ping-safe)
    `{prefix}linkscrubconfig @ everyone` - set the default role as the link role (ping-safe)
    `{prefix}linkscrubconfig @.everyone` - set the default role as the link role (ping-safe)
    `{prefix}linkscrubconfig @/everyone` - set the default role as the link role (ping-safe)
    """

    @command()
    @has_permissions(administrator=True)
    async def memberlogconfig(self, ctx, channel_mentions: discord.TextChannel):
        """Set the join/leave channel for a server by passing a channel mention"""
        with db.Session() as session:
            config = session.query(GuildMemberLog).filter_by(id=str(ctx.guild.id)).one_or_none()
            if config is not None:
                config.name = ctx.guild.name
                config.memberlog_channel = str(channel_mentions.id)
            else:
                config = GuildMemberLog(id=ctx.guild.id, memberlog_channel=channel_mentions.id, name=ctx.guild.name)
                session.add(config)
            await ctx.send(ctx.message.author.mention + ', memberlog settings configured!')
    memberconfig.example_usage = """
    `{prefix}memberlogconfig #join-leave-logs` - set a channel named #join-leave-logs to log joins/leaves 
    """

    @command()
    @has_permissions(administrator=True)
    async def messagelogconfig(self, ctx, channel_mentions: discord.TextChannel):
        """Set the modlog channel for a server by passing the channel id"""
        with db.Session() as session:
            config = session.query(GuildMessageLog).filter_by(id=str(ctx.guild.id)).one_or_none()
            if config is not None:
                config.name = ctx.guild.name
                config.messagelog_channel = str(channel_mentions.id)
            else:
                config = GuildMessageLog(id=ctx.guild.id, messagelog_channel=channel_mentions.id, name=ctx.guild.name)
                session.add(config)
            await ctx.send(ctx.message.author.mention + ', messagelog settings configured!')
    messagelogconfig.example_usage = """
    `{prefix}messagelogconfig #orwellian-dystopia` - set a channel named #orwellian-dystopia to log message edits/deletions
    """

class Mute(db.DatabaseObject):
    __tablename__ = 'mutes'
    id = db.Column(db.Integer, primary_key=True)
    guild = db.Column(db.Integer, primary_key=True)
    past_participle = "muted"


class Deafen(db.DatabaseObject):
    __tablename__ = 'deafens'
    id = db.Column(db.Integer, primary_key=True)
    guild = db.Column(db.Integer, primary_key=True)
    self_inflicted = db.Column(db.Boolean)
    past_participle = "deafened"


class GuildModLog(db.DatabaseObject):
    __tablename__ = 'modlogconfig'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)
    modlog_channel = db.Column(db.Integer, nullable=True)


class MemberRole(db.DatabaseObject):
    __tablename__ = 'member_roles'
    id = db.Column(db.Integer, primary_key=True)
    member_role = db.Column(db.Integer, nullable=True)


class GuildNewMember(db.DatabaseObject):
    __tablename__ = 'new_members'
    guild_id = db.Column(db.Integer, primary_key=True)
    channel_id = db.Column(db.Integer)
    role_id = db.Column(db.Integer)
    message = db.Column(db.String)


class GuildMemberLog(db.DatabaseObject):
    __tablename__ = 'memberlogconfig'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)
    memberlog_channel = db.Column(db.Integer)


class GuildMessageLog(db.DatabaseObject):
    __tablename__ = 'messagelogconfig'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)
    messagelog_channel = db.Column(db.Integer)


class GuildMessageLinks(db.DatabaseObject):
    __tablename__ = 'guild_msg_links'
    guild_id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, nullable=True)


def setup(bot):
    bot.add_cog(Moderation(bot))
