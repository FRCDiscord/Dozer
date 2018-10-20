"""Provides commands that pull information from The Orange Alliance, an FTC info API."""
import gzip
import pickle

import discord

from ._toa import *
from ._utils import *

embed_color = discord.Color(0xff9800)


class TOA(Cog):
    """TOA commands"""
    def __init__(self, bot):
        super().__init__(bot)
        self.parser = TOAParser(bot.config['toa']['key'], bot.http._session, app_name=bot.config['toa']['app_name'])
        # The line above has an error (bot.http._session is a protected class)
        with gzip.open("ftc_teams.pickle.gz") as f:
            self._teams = pickle.load(f)

    @group(invoke_without_command=True)
    async def toa(self, ctx, team_num: int):
        """
        Get FTC-related information from The Orange Alliance.
        If no subcommand is specified, the `team` subcommand is inferred, and the argument is taken as a team number.
        """
        await self.team.callback(self, ctx, team_num) # This works but Pylint throws an error

    toa.example_usage = """
    `{prefix}toa 5667` - show information on team 5667, the Robominers
    """

    @toa.command()
    @bot_has_permissions(embed_links=True)
    async def team(self, ctx, team_num: int):
        """Get information on an FTC team by number."""
        res = await self.parser.req("team/" + str(team_num))

        if len(json.loads(res))==0:
            await ctx.send("This team does not have any data on it yet, or it does not exist!")
            return

        team_data = json.loads(res)[0]

        e = discord.Embed(color=embed_color)
        e.set_author(name='FIRST® Tech Challenge Team {}'.format(team_num),
                     url='https://www.theorangealliance.org/teams/{}'.format(team_num),
                     icon_url='https://pbs.twimg.com/profile_images/1049159734249623553/SZ34vdcC_400x400.jpg')
        e.add_field(name='Name', value=team_data['team_name_short'])
        e.add_field(name='Rookie Year', value=team_data['rookie_year'])
        e.add_field(name='Location', value=', '.join((team_data['city'], team_data['state_prov'], team_data['country'])))
        e.add_field(name='Website', value=team_data['website'] or 'n/a')
        e.add_field(name='Team Info Page', value='https://www.theorangealliance.org/teams/{}'.format(team_data['team_key']))
        e.set_footer(text='Triggered by ' + ctx.author.display_name)
        await ctx.send('', embed=e)

    team.example_usage = """
    `{prefix}toa team 12670` - show information on team 12670, Eclipse
    """


def setup(bot):
    """Adds the TOA cog to the bot."""
    bot.add_cog(TOA(bot))
