"""Provides commands for pulling certain information."""
import math
import typing
from datetime import timezone, datetime, date
from difflib import SequenceMatcher

import discord
import humanize
from discord.ext.commands import cooldown, BucketType, guild_only
from discord_slash import cog_ext, SlashContext

from ._utils import *
from .levels import MemberXP, GuildXPSettings

blurple = discord.Color.blurple()
datetime_format = '%Y-%m-%d %H:%M:%S\nUTC'


class Info(Cog):
    """Commands for getting information about people and things on Discord."""

    @cog_ext.cog_slash(name="user", description="Returns user information")
    async def slash_member(self, ctx: SlashContext, member: discord.Member = None):
        """Users slash handler"""
        if member is None:
            member = ctx.guild.get_member(ctx.author.id)
        await self.member(ctx, member=member)

    @command(aliases=['user', 'memberinfo', 'userinfo'])
    @guild_only()
    @bot_has_permissions(embed_links=True)
    async def member(self, ctx, *, member: discord.Member = None):
        """Retrieve information about a member of the guild.
         If no arguments are passed, information about the author is used.
         **This command works without mentions.** Remove the '@' before your mention so you don't ping the person unnecessarily.
         You can pick a member by:
         - Username (`cooldude`)
         - Username and discriminator (`cooldude#1234`)
         - ID (`326749693969301506`)
         - Nickname - must be exact and is case-sensitive (`"Mr. Cool Dude III | Team 1234"`)
         - Mention (not recommended) (`@Mr Cool Dude III | Team 1234`)
         """
        if member is None:
            member = ctx.author
        footers = []

        levels_data = await MemberXP.get_by(guild_id=ctx.guild.id, user_id=member.id)
        levels_settings = await GuildXPSettings.get_by(guild_id=ctx.guild.id)
        levels_enabled = levels_settings[0].enabled if len(levels_settings) else False

        embed = discord.Embed(title=member.display_name, description=f'{member!s} ({member.id})', color=member.color)
        embed.set_thumbnail(url=member.avatar_url)
        embed.add_field(name='Bot Created' if member.bot else 'Account Created',
                        value=f"<t:{int(member.created_at.timestamp())}:f>", inline=True)

        if not levels_enabled:
            embed.add_field(name="Last Seen Here At", value="Levels Disabled")
        elif len(levels_data):

            #
            embed.add_field(name="Last Seen Here", value=f"<t:{int(levels_data[0].last_given_at.timestamp())}:R>")
            footers.append(f"Tracked Messages: {levels_data[0].total_messages}")
        else:
            embed.add_field(name="Last Seen Here At", value="Not available")
            footers.append("Tracked Messages: N/A")

        embed.add_field(name='Member Joined', value=f"<t:{int(member.joined_at.timestamp())}:f>", inline=True)
        if member.premium_since is not None:
            embed.add_field(name='Member Boosted', value=f"<t:{int(member.premium_since.timestamp())}:f>", inline=True)

        status = 'DND' if member.status is discord.Status.dnd else member.status.name.title()
        if member.status is not discord.Status.offline:
            platforms = self.pluralize([platform for platform in ('web', 'desktop', 'mobile') if
                                        getattr(member, f'{platform}_status') is not discord.Status.offline])
            status = f'{status} on {platforms}'
        activities = '\n'.join(self._format_activities(member.activities))
        if self.bot.config['presences_intents']:
            embed.add_field(name='Status and Activity', value=f'{status}\n{activities}', inline=False)
        for field_number, roles in enumerate(chunk(member.roles[:0:-1], 35)):
            embed.add_field(name='Roles', value=', '.join(role.mention for role in roles) or 'None', inline=False)
        footers.append(f"Color: {str(member.color).upper()}")
        embed.set_footer(text="; ".join(footers))
        await ctx.send(embed=embed)

    member.example_usage = """
    `{prefix}member`: show your member info
    `{prefix}member {ctx.me}`: show my member info
    """

    @staticmethod
    def _format_activities(activities: typing.Sequence[discord.Activity]) -> typing.List[str]:
        if not activities:
            return []

        def format_activity(activity: discord.Activity) -> str:
            if isinstance(activity, discord.CustomActivity):
                return f"{activity.emoji} | {activity.name}"
            elif isinstance(activity, discord.Spotify):
                return f"Listening to [{activity.title} by {activity.artist}](https://open.spotify.com/track/{activity.track_id}) on Spotify"
            elif activity.type is discord.ActivityType.listening:
                return f'Listening to {activity.name}'  # Special-cased to insert " to"
            else:
                activity_time = datetime.now(tz=timezone.utc) - activity.start.replace(tzinfo=timezone.utc)
                formatted_time = humanize.precisedelta(activity_time, minimum_unit='minutes', format="%0.1f")
                return f'{activity.type.name.capitalize()} {activity.name} {"`" + activity.details + "`" if activity.details else ""} ' \
                       f'for {formatted_time}'

        # Some games show up twice in the list (e.g. "Rainbow Six Siege" and "Tom Clancy's Rainbow Six Siege") so we
        # need to dedup them by string similarity before displaying them
        matcher = SequenceMatcher(lambda c: not c.isalnum(), autojunk=False)
        filtered = [activities[0]]
        for activity in activities[1:]:  # Expensive metadata is computed about seq2, so change it less frequently
            matcher.set_seq2(str(activity.name))  # Activity must be string, otherwise None will be passed into the matcher. An that breaks stuff
            for filtered_activity in filtered:
                matcher.set_seq1(str(filtered_activity.name))
                if matcher.quick_ratio() < 0.6 and matcher.ratio() < 0.6:  # Use quick_ratio if we can as ratio is slow
                    filtered.append(activity)
                    break

        return [format_activity(activity) for activity in filtered]

    @staticmethod
    def pluralize(values: typing.List[str]) -> str:
        """Inserts commas and "and"s in the right places to create a grammatically correct list."""
        if len(values) == 0:
            return ''
        elif len(values) == 1:
            return values[0]
        elif len(values) == 2:
            return f'{values[0]} and {values[1]}'
        else:
            return f'{", ".join(values[:-1])}, and {values[-1]}'

    @cog_ext.cog_subcommand(base="role", name="roleinfo", description="Returns role information")
    async def slash_role(self, ctx: SlashContext, role: discord.Role):
        """Role slash handler"""
        await self.role(ctx, role=role)

    @command()
    @guild_only()
    @cooldown(1, 10, BucketType.channel)
    async def role(self, ctx, role: discord.Role):
        """Retrieve info about a role in this guild"""
        embed = discord.Embed(title=f"Info for role: {role.name}", description=f"{role.mention} ({role.id})", color=role.color)
        embed.add_field(name="Created on", value=f"<t:{int(role.created_at.timestamp())}:f>")
        embed.add_field(name="Position", value=role.position)
        embed.add_field(name="Color", value=str(role.color).upper())
        embed.add_field(name="Assigned members", value=f"{len(role.members)}", inline=False)
        await ctx.send(embed=embed)

    @cog_ext.cog_subcommand(base="role", name="rolemembers", description="Returns all member who have a role")
    async def slash_rolemember(self, ctx: SlashContext, role: discord.Role):
        """rolemembers slash handler"""
        await self.rolemembers(ctx, role=role)

    @command()
    @guild_only()
    async def rolemembers(self, ctx, role: discord.Role):
        """Retrieve members who have this role"""
        embeds = []
        for page_num, page in enumerate(chunk(role.members, 10)):
            embed = discord.Embed(title=f"Members for role: {role.name}", color=role.color)
            embed.description = "\n".join(f"{member.mention}({member.id})" for member in page)
            embed.set_footer(text=f"Page {page_num + 1} of {math.ceil(len(role.members) / 10)}")
            embeds.append(embed)
        await paginate(ctx, embeds)

    @cog_ext.cog_slash(name="guild", description="Returns guild information")
    async def slash_guild(self, ctx: SlashContext):
        """Guild slash handler"""
        await self.guild(ctx)

    @guild_only()
    @cooldown(1, 10, BucketType.channel)
    @command(aliases=['server', 'guildinfo', 'serverinfo'])
    async def guild(self, ctx):
        """Retrieve information about this guild."""
        guild = ctx.guild
        static_emoji = sum(not e.animated for e in ctx.guild.emojis)
        animated_emoji = sum(e.animated for e in ctx.guild.emojis)
        embed = discord.Embed(title=f"Info for guild: {guild.name}", description=f"Members: {guild.member_count}", color=blurple)

        embed.set_thumbnail(url=guild.icon_url)

        embed.add_field(name='Created on', value=f"<t:{int(guild.created_at.timestamp())}:f>")
        embed.add_field(name='Owner', value=guild.owner)
        embed.add_field(name='Emoji', value="{} static, {} animated".format(static_emoji, animated_emoji))
        embed.add_field(name='Roles', value=str(len(guild.roles) - 1))  # Remove @everyone
        embed.add_field(name='Channels', value=str(len(guild.channels)))
        embed.add_field(name='Nitro Boost Info', value=f'Level {ctx.guild.premium_tier}, '
                                                       f'{ctx.guild.premium_subscription_count} booster(s), '
                                                       f'{ctx.guild.filesize_limit // 1024 ** 2}MiB files, '
                                                       f'{ctx.guild.bitrate_limit / 1000:0.1f}kbps voice')

        await ctx.send(embed=embed)

    guild.example_usage = """
    `{prefix}guild` - get information about this guild
    """


def setup(bot):
    """Adds the info cog to the bot"""
    bot.add_cog(Info(bot))
