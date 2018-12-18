"""Provides commands for voice, currently only voice and text channel access bindings."""
import discord
from discord.ext.commands import has_permissions

from ._utils import *
from .. import db


class Voice(Cog):
    """Commands interacting with voice."""
    async def on_voice_state_update(self, member, before, after):
        """Handles voicebinds when members join/leave voice channels"""
        # skip this if we have no perms, or if it's something like a mute/deafen
        if member.guild.me.guild_permissions.manage_roles and before.channel != after.channel:
            # determine if it's a join/leave event as well.
            # before and after are voice states
            if after.channel is not None:
                # join event, give role
                with db.Session() as session:
                    config = session.query(Voicebinds).filter_by(channel_id=after.channel.id).one_or_none()
                    if config is not None:
                        await member.add_roles(member.guild.get_role(config.role_id))

            if before.channel is not None:
                # leave event, take role
                with db.Session() as session:
                    config = session.query(Voicebinds).filter_by(channel_id=before.channel.id).one_or_none()
                    if config is not None:
                        await member.remove_roles(member.guild.get_role(config.role_id))

    @command()
    @bot_has_permissions(manage_roles=True)
    @has_permissions(manage_roles=True)
    async def voicebind(self, ctx, voice_channel: discord.VoiceChannel, *, role: discord.Role):
        """Associates a voice channel with a role, so users joining a voice channel will automatically be given a specified role or roles."""

        with db.Session() as session:
            config = session.query(Voicebinds).filter_by(channel_id=voice_channel.id).one_or_none()
            if config is not None:
                config.guild_id = ctx.guild.id
                config.channel_id = voice_channel.id
                config.role_id = role.id
            else:
                config = Voicebinds(channel_id=voice_channel.id, role_id=role.id, guild_id=ctx.guild.id)
                session.add(config)

        await ctx.send("Role `{role}` will now be given to users in voice channel `{voice_channel}`!".format(role=role,
                                                                                                             voice_channel=voice_channel))

    voicebind.example_usage = """
    `{prefix}voicebind "General #1" voice-general-1` - sets up Dozer to give users  `voice-general-1` when they join voice channel "General #1", which will be removed when they leave.
    """

    @command()
    @bot_has_permissions(manage_roles=True)
    @has_permissions(manage_roles=True)
    async def voiceunbind(self, ctx, voice_channel: discord.VoiceChannel):
        """Dissasociates a voice channel with a role previously binded with the voicebind command."""
        with db.Session() as session:
            config = session.query(Voicebinds).filter_by(channel_id=voice_channel.id).one_or_none()
            if config is not None:
                role = ctx.guild.get_role(config.role_id)
                session.delete(config)
                await ctx.send(
                    "Role `{role}` will no longer be given to users in voice channel `{voice_channel}`!".format(
                        role=role, voice_channel=voice_channel))
            else:
                await ctx.send("It appears that `{voice_channel}` is not associated with a role!".format(
                    voice_channel=voice_channel))

    voiceunbind.example_usage = """
    `{prefix}voiceunbind "General #1"` - Removes automatic role-giving for users in "General #1".
    """

    @command()
    @bot_has_permissions(manage_roles=True)
    async def voicebindlist(self, ctx):
        """Lists all the voice channel to role bindings for the current server"""
        embed = discord.Embed(title="List of voice bindings for \"{}\"".format(ctx.guild), color=discord.Color.blue())
        with db.Session() as session:
            for config in session.query(Voicebinds).filter_by(guild_id=ctx.guild.id).all():
                channel = discord.utils.get(ctx.guild.voice_channels, id=config.channel_id)
                role = ctx.guild.get_role(config.role_id)
                embed.add_field(name=channel, value="`{}`".format(role))
        await ctx.send(embed=embed)

    voicebindlist.example_usage = """
    `{prefix}voicebindlist` - Lists all the voice channel to role bindings for the current server bound with the voicebind command.
    """


class Voicebinds(db.DatabaseObject):
    """DB object to keep track of voice to text channel access bindings."""
    __tablename__ = 'voicebinds'
    id = db.Column(db.Integer, primary_key=True)
    guild_id = db.Column(db.Integer)
    channel_id = db.Column(db.Integer)
    role_id = db.Column(db.Integer)


def setup(bot):
    """Add this cog to the main bot."""
    bot.add_cog(Voice(bot))
