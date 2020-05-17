"""Provides commands for pulling certain information."""
from difflib import SequenceMatcher
import typing
import discord
from discord.ext.commands import cooldown, BucketType, guild_only

from ._utils import *

blurple = discord.Color.blurple()
datetime_format = '%Y-%m-%d %I:%M %p'


class Info(Cog):
    """Commands for getting information about people and things on Discord."""
    datetime_format = '%Y-%m-%d %H:%M:%S UTC'

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

        icon_url = member.avatar_url_as(static_format='png')

        embed = discord.Embed(title=member.display_name, description=f'{member!s} ({member.id})', color=member.color)
        embed.add_field(name='Bot Created' if member.bot else 'Account Created',
                        value=member.created_at.strftime(self.datetime_format), inline=True)
        embed.add_field(name='Member Joined', value=member.joined_at.strftime(self.datetime_format), inline=True)
        if member.premium_since is not None:
            embed.add_field(name='Member Boosted', value=member.premium_since.strftime(self.datetime_format), inline=True)
        embed.add_field(name='Color', value=str(member.color).upper(), inline=True)

        status = 'DND' if member.status is discord.Status.dnd else member.status.name.title()
        if member.status is not discord.Status.offline:
            platforms = self.pluralize([platform for platform in ('web', 'desktop', 'mobile') if
                                        getattr(member, f'{platform}_status') is not discord.Status.offline])
            status = f'{status} on {platforms}'
        activities = '\n'.join(self._format_activities(member.activities))
        embed.add_field(name='Status and Activity', value=f'{status}\n{activities}', inline=True)

        embed.add_field(name='Roles', value=', '.join(role.name for role in member.roles[:0:-1]) or 'None')
        embed.add_field(name='Icon URL', value=icon_url)
        embed.set_thumbnail(url=icon_url)
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
                return f"{activity.emoji} {activity.name}"
            elif isinstance(activity, discord.Spotify):
                return f'Listening to {activity.title} by {activity.artist} on Spotify'
            elif activity.type is discord.ActivityType.listening:
                return f'Listening to {activity.name}'  # Special-cased to insert " to"
            else:
                return f'{activity.type.name.capitalize()} {activity.name}'

        # Some games show up twice in the list (e.g. "Rainbow Six Siege" and "Tom Clancy's Rainbow Six Siege") so we
        # need to dedup them by string similarity before displaying them
        matcher = SequenceMatcher(lambda c: not c.isalnum(), autojunk=False)
        filtered = [activities[0]]
        for activity in activities[1:]:
            matcher.set_seq2(activity.name)  # Expensive metadata is computed about seq2, so change it less frequently
            for filtered_activity in filtered:
                matcher.set_seq1(filtered_activity.name)
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

    @guild_only()
    @cooldown(1, 10, BucketType.channel)
    @command(aliases=['server', 'guildinfo', 'serverinfo'])
    async def guild(self, ctx):
        """Retrieve information about this guild."""
        guild = ctx.guild
        static_emoji = sum(not e.animated for e in ctx.guild.emojis)
        animated_emoji = sum(e.animated for e in ctx.guild.emojis)
        e = discord.Embed(color=blurple)
        e.set_thumbnail(url=guild.icon_url)
        e.add_field(name='Name', value=guild.name)
        e.add_field(name='ID', value=guild.id)
        e.add_field(name='Created at', value=guild.created_at.strftime(datetime_format))
        e.add_field(name='Owner', value=guild.owner)
        e.add_field(name='Members', value=guild.member_count)
        e.add_field(name='Channels', value=str(len(guild.channels)))
        e.add_field(name='Roles', value=str(len(guild.roles) - 1))  # Remove @everyone
        e.add_field(name='Emoji', value="{} static, {} animated".format(static_emoji, animated_emoji))
        e.add_field(name='Region', value=guild.region.name)
        e.add_field(name='Icon URL', value=guild.icon_url or 'This guild has no icon.')
        e.add_field(name='Nitro Boost', value=f'Level {ctx.guild.premium_tier}, '
                                              f'{ctx.guild.premium_subscription_count} booster(s)\n'
                                              f'{ctx.guild.filesize_limit // 1024**2}MiB files, '
                                              f'{ctx.guild.bitrate_limit / 1000:0.1f}kbps voice')

        await ctx.send(embed=e)

    guild.example_usage = """
    `{prefix}guild` - get information about this guild
    """


def setup(bot):
    """Adds the info cog to the bot"""
    bot.add_cog(Info(bot))
