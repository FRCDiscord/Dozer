"""Provides commands for pulling certain information."""
import discord
from discord.ext.commands import cooldown, BucketType, guild_only

from ._utils import *

blurple = discord.Color.blurple()
datetime_format = '%Y-%m-%d %I:%M %p'


class Info(Cog):
    """Commands for getting information about people and things on Discord."""

    @guild_only()
    @cooldown(1, 10, BucketType.channel)
    @command(aliases=['user', 'userinfo', 'memberinfo'])
    async def member(self, ctx, member: discord.Member = None):
        """
        Retrieve information about a member of the guild.
        If no arguments are passed, information about the author is used.
        **This command works without mentions.** Remove the '@' before your mention so you don't ping the person unnecessarily.
        You can pick a member by:
        - Username (`cooldude`)
        - Username and discriminator (`cooldude#1234`)
        - ID (`326749693969301506`)
        - Nickname - must be exact and is case-sensitive (`"Mr. Cool Dude III | Team 1234"`)
        - Mention (not recommended) (`@Mr Cool Dude III | Team 1234`)
        """
        async with ctx.typing():
            member = member or ctx.author
            icon_url = member.avatar_url_as(static_format='png')
            e = discord.Embed(color=member.color)
            e.set_thumbnail(url=icon_url)
            e.add_field(name='Name', value=str(member))
            e.add_field(name='ID', value=member.id)
            e.add_field(name='Nickname', value=member.nick, inline=member.nick is None)
            e.add_field(name='Bot Created' if member.bot else 'User Joined Discord',
                        value=member.created_at.strftime(datetime_format))
            e.add_field(name='Joined Guild', value=member.joined_at.strftime(datetime_format))
            e.add_field(name='Color', value=str(member.color).upper())

            e.add_field(name='Status and Game', value=f'{member.status}, '.title() + (
                f'playing {member.game}' if member.game else 'no game playing'), inline=False)
            roles = sorted(member.roles, reverse=True)[:-1]  # Remove @everyone
            e.add_field(name='Roles', value=', '.join(role.name for role in roles) or "No roles", inline=False)
            e.add_field(name='Icon URL', value=icon_url, inline=False)
        await ctx.send(embed=e)

    member.example_usage = """
    `{prefix}member` - get information about yourself
    `{prefix}member cooldude#1234` - get information about cooldude
    """

    @guild_only()
    @cooldown(1, 10, BucketType.channel)
    @command(aliases=['server', 'guildinfo', 'serverinfo'])
    async def guild(self, ctx):
        """Retrieve information about this guild."""
        guild = ctx.guild
        e = discord.Embed(color=blurple)
        e.set_thumbnail(url=guild.icon_url)
        e.add_field(name='Name', value=guild.name)
        e.add_field(name='ID', value=guild.id)
        e.add_field(name='Created at', value=guild.created_at.strftime(datetime_format))
        e.add_field(name='Owner', value=guild.owner)
        e.add_field(name='Members', value=guild.member_count)
        e.add_field(name='Channels', value=len(guild.channels))
        e.add_field(name='Roles', value=len(guild.role_hierarchy) - 1)  # Remove @everyone
        e.add_field(name='Emoji', value=len(guild.emojis))
        e.add_field(name='Region', value=guild.region.name)
        e.add_field(name='Icon URL', value=guild.icon_url or 'This guild has no icon.')
        await ctx.send(embed=e)

    guild.example_usage = """
    `{prefix}guild` - get information about this guild
    """


def setup(bot):
    """Adds the info cog to the bot"""
    bot.add_cog(Info(bot))
