"""Commands for making and seeing robotics team associations."""

import collections
import json
import discord
from discord.ext.commands import BadArgument, guild_only

from ._utils import *
from .. import db
from .tba import TBA
from .toa import TOA


class Teams(Cog):
    """Commands for making and seeing robotics team associations."""
    @command()
    async def setteam(self, ctx, team_type, team_number: int):
        """Sets an association with your team in the database."""
        team_type = team_type.casefold()
        dbcheck = await TeamNumbers.get_by(user_id=ctx.author.id, team_type=team_type, team_number=team_number)
        if not dbcheck:
            await TeamNumbers(user_id=ctx.author.id, team_number=team_number, team_type=team_type).update_or_add()
            await ctx.send("Team number set!")
        else:
            raise BadArgument("You are already associated with that team!")

    setteam.example_usage = """
    `{prefix}setteam type team_number` - Creates an association in the database with a specified team
    """

    @command()
    async def removeteam(self, ctx, team_type, team_number: int):
        """Removes an association with a team in the database."""
        team_type = team_type.casefold()
        results = await TeamNumbers.get_by(user_id=ctx.author.id, team_type=team_type, team_number=team_number)
        if len(results) != 0:
            await TeamNumbers.delete(user_id=ctx.author.id, team_number=team_number, team_type=team_type)
            await ctx.send("Removed association with {} team {}".format(team_type, team_number))
        else:
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
        teams = await TeamNumbers.get_by(user_id=user.id)
        if len(teams) == 0:
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

    @command()
    @guild_only()
    async def compcheck(self, ctx, event_type: str, event_key):
        """Allows you to see people in the Discord server that are going to a certain competition."""
        if event_type.lower() == "frc":
            teams_raw = await TBA(ctx.bot).session.event_teams(event_key)
            teams = [team.team_number for team in teams_raw]
        elif event_type.lower() == "ftc":
            teams_raw = json.loads(await TOA(ctx.bot).parser.req(f"/api/event/{event_key}/teams"))
            teams = [team['team']['team_number'] for team in teams_raw]
        else:
            raise BadArgument("Unknown event type!")
        found_mems = False
        e = discord.Embed(type='rich')
        e.title = 'Members going to {}'.format(event_key)
        for team in teams:
            members = await TeamNumbers.get_by(team_type=event_type.lower(), team_number=team)
            memstr = ""
            for member in members:
                mem = ctx.guild.get_member(member.user_id)
                if mem is not None:
                    newmemstr = "{} {} \n".format(mem.display_name, mem.mention)
                    if len(newmemstr + memstr) > 1023:
                        e.add_field(name=f"Team {team}", value=memstr)
                        memstr = ""
                    memstr += newmemstr
                    found_mems = True
            if len(memstr) > 0:
                if len(e.fields) == 25:
                    await ctx.send(embed=e)
                    e = discord.Embed(type='rich')
                    e.title = 'Members going to {}'.format(event_key)
                e.add_field(name=f"Team {team}", value=memstr)

        if not found_mems:
            raise BadArgument("Couldn't find any team members for that event!")
        else:
            await ctx.send(embed=e)

    teamsfor.example_usage = """
    `{prefix}teamsfor member` - Returns all team associations with the mentioned user. Assumes caller if blank.
    """

    @group(invoke_without_command=True)
    @guild_only()
    async def onteam(self, ctx, team_type, team_number: int):
        """Allows you to see who has associated themselves with a particular team."""
        team_type = team_type.casefold()
        users = await TeamNumbers.get_by(team_type=team_type, team_number=team_number)
        if len(users) == 0:
            await ctx.send("Nobody on that team found!")
        else:
            e = discord.Embed(type='rich')
            e.title = 'Users on team {}'.format(team_number)
            e.description = "Users: \n"
            extra_mems = ""
            for i in users:
                user = ctx.guild.get_member(i.user_id)
                if user is not None:
                    memstr = "{} {} \n".format(user.display_name, user.mention)
                    if len(e.description + memstr) > 2047:
                        extra_mems += memstr
                    else:
                        e.description = e.description + memstr
            if len(extra_mems) != 0:
                e.add_field(name="Users on team {}".format(team_number), value=extra_mems)
            await ctx.send(embed=e)

    onteam.example_usage = """
    `{prefix}onteam type team_number` - Returns a list of users associated with a given team type and number
    """

    @onteam.command()
    @guild_only()
    async def top(self, ctx):
        """Show the top 10 teams by number of members in this guild."""
        users = [mem.id for mem in ctx.guild.members]
        counts = await TeamNumbers.top10(users)
        embed = discord.Embed(title=f'Top teams in {ctx.guild.name}', color=discord.Color.blue())
        embed.description = '\n'.join(
            f'{type_.upper()} team {num} ({count} member{"s" if count > 1 else ""})' for (type_, num, count) in counts)
        await ctx.send(embed=embed)

    top.example_usage = """
    `{prefix}onteam top` - List the 10 teams with the most members in this guild
    """

    @Cog.listener('on_member_join')
    async def on_member_join(self, member):
        """Adds a user's team association to their name when they join (if exactly 1 association)"""
        if member.guild.me.guild_permissions.manage_nicknames:
            query = await TeamNumbers.get_by(user_id=member.id)
            if len(query) == 1:
                nick = "{} {}{}".format(member.display_name, query[0].team_type, query[0].team_number)
                if len(nick) <= 32:
                    await member.edit(nick=nick)


class TeamNumbers(db.DatabaseTable):
    """Database operations for tracking team associations."""
    __tablename__ = 'team_numbers'
    __uniques__ = 'user_id, team_number, team_type'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            user_id bigint NOT NULL,
            team_number bigint NOT NULL,
            team_type VARCHAR NOT NULL,
            PRIMARY KEY (user_id, team_number, team_type)
            )""")

    def __init__(self, user_id, team_number, team_type):
        super().__init__()
        self.user_id = user_id
        self.team_number = team_number
        self.team_type = team_type

    async def update_or_add(self):
        """Assign the attribute to this object, then call this method to either insert the object if it doesn't exist in
        the DB or update it if it does exist. It will update every column not specified in __uniques__."""
        # This is its own functions because all columns must be unique, which breaks the syntax of the other one
        keys = []
        values = []
        for var, value in self.__dict__.items():
            # Done so that the two are guaranteed to be in the same order, which isn't true of keys() and values()
            if value is not None:
                keys.append(var)
                values.append(value)
        async with db.Pool.acquire() as conn:
            statement = f"""
            INSERT INTO {self.__tablename__} ({", ".join(keys)})
            VALUES({','.join(f'${i+1}' for i in range(len(values)))}) 
            """
            await conn.execute(statement, *values)

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = TeamNumbers(user_id=result.get("user_id"),
                              team_number=result.get("team_number"),
                              team_type=result.get("team_type"))
            result_list.append(obj)
        return result_list

    # noinspection SqlResolve
    @classmethod
    async def top10(cls, user_ids):
        """Returns the top 10 team entries"""
        query = f"""SELECT team_type, team_number, count(*)
                FROM {cls.__tablename__}
                WHERE user_id = ANY($1) --first param: list of user IDs
                GROUP BY team_type, team_number
                ORDER BY count DESC, team_type, team_number
                LIMIT 10"""
        async with db.Pool.acquire() as conn:
            return await conn.fetch(query, user_ids)


def setup(bot):
    """Adds this cog to the main bot"""
    bot.add_cog(Teams(bot))
