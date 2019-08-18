"""Commands for making and seeing robotics team associations."""

import collections
import discord
from discord.ext.commands import BadArgument, guild_only

from ._utils import *
from .. import db


class Teams(Cog):
    """Commands for making and seeing robotics team associations."""
    @command()
    async def setteam(self, ctx, team_type, team_number: int):
        """Sets an association with your team in the database."""
        team_type = team_type.casefold()
        with db.Session() as session:
            dbcheck = session.query(TeamNumbers).filter_by(user_id=ctx.author.id, team_number=team_number,
                                                           team_type=team_type).one_or_none()
            if dbcheck is None:
                dbtransaction = TeamNumbers(user_id=ctx.author.id, team_number=team_number, team_type=team_type)
                session.add(dbtransaction)
                await ctx.send("Team number set!")
            else:
                raise BadArgument("You are already associated with that team!")

    setteam.example_usage = """
    `{prefix}setteam type team_number` - Creates an association in the database with a specified team
    """

    @command()
    async def removeteam(self, ctx, team_type, team_number):
        """Removes an association with a team in the database."""
        team_type = team_type.casefold()
        with db.Session() as session:
            results = session.query(TeamNumbers).filter_by(user_id=ctx.author.id, team_type=team_type,
                                                           team_number=team_number).one_or_none()
            if results is not None:
                session.delete(results)
                await ctx.send("Removed association with {} team {}".format(team_type, team_number))
            if results is None:
                await ctx.send("Couldn't find any associations with that team!")

    removeteam.example_usage = """
    `{prefix}removeteam type team_number` - Removes your associations with a specified team
    """

    @command()
    @guild_only()
    async def teamsfor(self, ctx, user: discord.Member = None):
        """Allows you to see the teams for the mentioned user. If no user is mentioned, your teams are displayed."""
        if user is None:
            user = ctx.author
        with db.Session() as session:
            teams = session.query(TeamNumbers).filter_by(user_id=user.id).order_by("team_type desc",
                                                                                   "team_number asc").all()
            if not teams:
                raise BadArgument("Couldn't find any team associations for that user!")
            else:
                e = discord.Embed(type='rich')
                e.title = 'Teams for {}'.format(user.display_name)
                e.description = "Teams: \n"
                for i in teams:
                    e.description = "{} {} Team {} \n".format(e.description, i.team_type.upper(), i.team_number)
                await ctx.send(embed=e)

    teamsfor.example_usage = """
    `{prefix}teamsfor member` - Returns all team associations with the mentioned user. Assumes caller if blank.
    """

    @group(invoke_without_command=True)
    @guild_only()
    async def onteam(self, ctx, team_type, team_number):
        """Allows you to see who has associated themselves with a particular team."""
        team_type = team_type.casefold()
        with db.Session() as session:
            users = session.query(TeamNumbers).filter_by(team_number=team_number, team_type=team_type).all()
            if not users:
                await ctx.send("Nobody on that team found!")
            else:
                e = discord.Embed(type='rich')
                e.title = 'Users on team {}'.format(team_number)
                e.description = "Users: \n"
                for i in users:
                    user = ctx.guild.get_member(i.user_id)
                    if user is not None:
                        e.description = "{}{} {} \n".format(e.description, user.display_name, user.mention)
                await ctx.send(embed=e)

    onteam.example_usage = """
    `{prefix}onteam type team_number` - Returns a list of users associated with a given team type and number
    """

    @onteam.command()
    @guild_only()
    async def top(self, ctx):
        """Show the top 10 teams by number of members in this guild."""
        with db.Session() as session:
            team_keys = session.query(TeamNumbers.team_type, TeamNumbers.team_number) \
                .filter(TeamNumbers.user_id.in_({member.id for member in ctx.guild.members})).all()

        counts = sorted(collections.Counter(team_keys).most_common(10), key=lambda tup: tup[0])
        embed = discord.Embed(title=f'Top teams in {ctx.guild.name}', color=discord.Color.blue())
        embed.description = '\n'.join(
            f'{type_.upper()} team {num} ({count} member{"s" if count > 1 else ""})' for (type_, num), count in counts)
        await ctx.send(embed=embed)

    top.example_usage = """
    `{prefix}onteam top` - List the 10 teams with the most members in this guild
    """

    async def on_member_join(self, member):
        """Adds a user's team association to their name when they join (if exactly 1 association)"""
        if member.guild.me.guild_permissions.manage_nicknames:
            with db.Session() as session:
                query = session.query(TeamNumbers).filter_by(user_id=member.id).first()
                if query is not None:
                    nick = "{} {}{}".format(member.display_name, query.team_type, query.team_number)
                    if len(nick) <= 32:
                        await member.edit(nick=nick)


class TeamNumbers(db.DatabaseObject):
    """DB object for tracking team associations."""
    __tablename__ = 'team_numbers'
    user_id = db.Column(db.BigInteger, primary_key=True)
    team_number = db.Column(db.BigInteger, primary_key=True)
    team_type = db.Column(db.String, primary_key=True)


def setup(bot):
    """Adds this cog to the main bot"""
    bot.add_cog(Teams(bot))
