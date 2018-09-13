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

        if not bot.config['toa']['teamdata_url']:
            with gzip.open("ftc_teams.pickle.gz") as f:
                self._teams = pickle.load(f)
        else:
            self._teams = None

    async def get_teamdata(self, team_num: int):
        if self._teams is None:
            async with async_timeout.timeout(5) as _, self.bot.http._session.get(urljoin(self.bot.config['toa']['teamdata_url'], str(team_num))) as response:
                data = await response.json() if response.status < 400 else {}
        else:
            data = self._teams.get(team_num, {})

        return data

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
        # Fun fact: this no longer actually queries TOA. It queries a server that provides FIRST data.
        team_data = await self.get_teamdata(team_num) #await self.parser.req("team/" + str(team_num))
        if not team_data:
            # rip
            await ctx.send("This team does not have any data on it yet, or it does not exist!")
            return

        season_data = team_data['seasons'][0]

        # many team entries lack a valid url
        website = (season_data['website']).strip()
        if website and not (website.startswith("http://") or website.startswith("https://")):
            website = "http://" + website
        e = discord.Embed(color=embed_color,
                          title=f'FIRST® Tech Challenge Team {team_num}',
                          url=f'https://www.theorangealliance.org/teams/{team_num}')
                          #icon_url='https://cdn.discordapp.com/icons/342152047753166859/de4d258c0cab5bee0b04d406172ec585.jpg')
        e.add_field(name='Name', value=season_data["name"])
        e.add_field(name='Rookie Year', value=team_data['rookie_year'])
        e.add_field(name='Location', value=', '.join((season_data["city"], season_data["state_prov"], season_data["country"])))
        e.add_field(name='Website', value=website or 'n/a')
        #e.add_field(name='Team Info Page', value=f'https://www.theorangealliance.org/teams/{team_num}')
        e.set_footer(text='Triggered by ' + ctx.author.display_name)
        await ctx.send('', embed=e)

    team.example_usage = """
    `{prefix}toa team 12670` - show information on team 12670, Eclipse
    """


def setup(bot):
    """Adds the TOA cog to the bot."""
    bot.add_cog(TOA(bot))
