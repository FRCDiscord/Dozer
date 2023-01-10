"""Provides commands for voice, currently only voice and text channel access bindings."""
import discord
from discord.ext.commands import has_permissions, BadArgument
from discord.utils import escape_markdown

from dozer.context import DozerContext
from ._utils import *
from .info import blurple
from .. import db


class Voice(Cog):
    """Commands interacting with voice."""

    @staticmethod
    async def auto_ptt_check(voice_channel: discord.VoiceChannel):
        """Handles voice activity when members join/leave voice channels"""
        total_users = len(voice_channel.channel.members)
        config = await AutoPTT.get_by(channel_id=voice_channel.channel.id)
        if config:
            everyone = voice_channel.channel.guild.default_role  # grab the @everyone role
            perms = voice_channel.channel.overwrites_for(everyone)  # grab the @everyone overwrites
            if total_users > config[0].ptt_limit:
                perms.update(use_voice_activation=False)  # Force PTT enable
            if total_users <= config[0].ptt_limit:
                perms.update(use_voice_activation=None)  # Set PTT to neutral
            await voice_channel.channel.set_permissions(target=everyone, overwrite=perms)

    @Cog.listener('on_voice_state_update')  # Used for VoiceBind
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState,
                                    after: discord.VoiceState):
        """Handles voicebinds when members join/leave voice channels"""
        # skip this if we have no perms, or if it's something like a mute/deafen
        if member.guild.me.guild_permissions.manage_roles and before.channel != after.channel:
            # determine if it's a join/leave event as well.
            # before and after are voice states
            if before.channel is not None:
                # leave event, take role
                config = await Voicebinds.get_by(channel_id=before.channel.id)
                if len(config) != 0:
                    await member.remove_roles(member.guild.get_role(config[0].role_id))
            if after.channel is not None:
                # join event, give role
                config = await Voicebinds.get_by(channel_id=after.channel.id)
                if len(config) != 0:
                    await member.add_roles(member.guild.get_role(config[0].role_id))

    @Cog.listener('on_voice_state_update')  # Used for auto PTT
    async def on_PTT_check(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Runs the autoPTTcheck when a user leaves and/or joins a vc"""
        # skip this if we have no perms to edit voice channel
        total_users = 0
        if member.guild.me.guild_permissions.manage_channels and before.channel != after.channel:
            # determine if it's a join/leave event as well.
            # before and after are voice states
            if before.channel is not None:
                # leave event, take role
                await self.auto_ptt_check(before)
            if after.channel is not None:
                # join event, give role
                await self.auto_ptt_check(after)

    @command()
    @bot_has_permissions(manage_channels=True)
    @has_permissions(manage_channels=True)
    async def autoptt(self, ctx: DozerContext, voice_channel: discord.VoiceChannel, ptt_threshold: int):
        """Configures AutoPtt limit for when members join/leave voice channels ptt is enabled"""

        e = discord.Embed(color=blurple)
        e.set_footer(text='Triggered by ' + escape_markdown(ctx.author.display_name))

        if ptt_threshold < 0:
            raise BadArgument('PTT threshold must be positive integer')

        if ptt_threshold == 0:
            config = await AutoPTT.get_by(channel_id=voice_channel.id)
            if len(config) != 0:
                await AutoPTT.delete(channel_id=config[0].channel_id)
                e.add_field(name='Success!', value=f'AutoPTT has been disabled for voice channel "**{voice_channel}**"')
            else:
                e.add_field(name='Error', value=f'AutoPTT has not been configured for voice channel "**{voice_channel}**"')
        else:
            ent = AutoPTT(
                channel_id=voice_channel.id,
                ptt_limit=ptt_threshold
            )

            await ent.update_or_add()

            e.add_field(name='Success!', value=f'Voice Channel **{voice_channel}**\'s PTT threshold set to {ptt_threshold} members')

        await ctx.send(embed=e)

    autoptt.example_usage = """
        `{prefix}autoptt "General #1" 15 - sets up Dozer to give force Push-To-Talk when more than 15 users joins a voice channel.
        `{prefix}autoptt "General #1" 0 - disables AutoPTT for General #1.
        """

    @command()
    @bot_has_permissions(manage_roles=True)
    @has_permissions(manage_roles=True)
    async def voicebind(self, ctx: DozerContext, voice_channel: discord.VoiceChannel, *, role: discord.Role):
        """Binds a voice channel with a role, so users joining voice channels will be given desired role(s)."""

        config = await Voicebinds.get_by(channel_id=voice_channel.id)
        if len(config) != 0:
            config[0].guild_id = ctx.guild.id
            config[0].channel_id = voice_channel.id
            config[0].role_id = role.id
            await config[0].update_or_add()
        else:
            await Voicebinds(channel_id=voice_channel.id, role_id=role.id, guild_id=ctx.guild.id).update_or_add()

        await ctx.send(f"Role `{role}` will now be given to users in voice channel `{voice_channel}`!")

    voicebind.example_usage = """
    `{prefix}voicebind "General #1" voice-general-1` - sets up Dozer to give users  `voice-general-1` when they join voice channel "General #1", which will be removed when they leave.
    """

    @command()
    @bot_has_permissions(manage_roles=True)
    @has_permissions(manage_roles=True)
    async def voiceunbind(self, ctx: DozerContext, voice_channel: discord.VoiceChannel):
        """Dissasociates a voice channel with a role previously binded with the voicebind command."""
        config = await Voicebinds.get_by(channel_id=voice_channel.id)
        if len(config) != 0:
            role = ctx.guild.get_role(config[0].role_id)
            await Voicebinds.delete(id=config[0].id)
            await ctx.send(f"Role `{role}` will no longer be given to users in voice channel `{voice_channel}`!")
        else:
            await ctx.send(f"It appears that `{voice_channel}` is not associated with a role!")

    voiceunbind.example_usage = """
    `{prefix}voiceunbind "General #1"` - Removes automatic role-giving for users in "General #1".
    """

    @command()
    @bot_has_permissions(manage_roles=True)
    async def voicebindlist(self, ctx: DozerContext):
        """Lists all the voice channel to role bindings for the current server"""
        embed = discord.Embed(title=f"List of voice bindings for \"{ctx.guild}\"", color=discord.Color.blue())
        for config in await Voicebinds.get_by(guild_id=ctx.guild.id):
            channel = discord.utils.get(ctx.guild.voice_channels, id=config.channel_id)
            role = ctx.guild.get_role(config.role_id)
            embed.add_field(name=channel, value=f"`{role}`")
        await ctx.send(embed=embed)

    voicebindlist.example_usage = """
    `{prefix}voicebindlist` - Lists all the voice channel to role bindings for the current server bound with the voicebind command.
    """


class Voicebinds(db.DatabaseTable):
    """DB object to keep track of voice to text channel access bindings."""
    __tablename__ = 'voicebinds'

    __uniques__ = 'id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            id SERIAL PRIMARY KEY NOT NULL,
            guild_id bigint NOT NULL,
            channel_id bigint null,
            role_id bigint null
            )""")

    def __init__(self, guild_id: int, channel_id: int, role_id: int, row_id: int = None):
        super().__init__()
        if row_id is not None:
            self.id = row_id
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.role_id = role_id

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = Voicebinds(row_id=result.get("id"),
                             guild_id=result.get("guild_id"),
                             channel_id=result.get("channel_id"),
                             role_id=result.get("role_id"))
            result_list.append(obj)
        return result_list


class AutoPTT(db.DatabaseTable):
    """DB object to keep track of voice to text channel access bindings."""
    __tablename__ = 'autoptt'
    __uniques__ = 'channel_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            channel_id bigint PRIMARY KEY NOT NULL,
            ptt_limit bigint null
            )""")

    def __init__(self, channel_id: int, ptt_limit: int):
        super().__init__()
        self.channel_id = channel_id
        self.ptt_limit = ptt_limit

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = AutoPTT(
                channel_id=result.get("channel_id"),
                ptt_limit=result.get("ptt_limit"))
            result_list.append(obj)
        return result_list


async def setup(bot):
    """Add this cog to the main bot."""
    await bot.add_cog(Voice(bot))
