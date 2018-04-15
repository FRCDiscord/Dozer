import gzip
import pickle

import discord
from discord.ext.commands import bot_has_permissions

from ._toa import *
from ._utils import *

embed_color = discord.Color(0xff9800)


class TOA(Cog):
    def __init__(self, bot):
        super().__init__(bot)
        self.parser = TOAParser(bot.config['toa']['key'], bot.http._session, app_name=bot.config['toa']['app_name'])
        with gzip.open("ftc_teams.pickle.gz") as f:
            self._teams = pickle.load(f)

    @group(invoke_without_command=True)
    async def toa(self, ctx, team_num: int):
        """
        Get FTC-related information from The Orange Alliance.
        If no subcommand is specified, the `team` subcommand is inferred, and the argument is taken as a team number.
        """
        await self.team.callback(self, ctx, team_num)

    toa.example_usage = """
    `{prefix}toa 5667` - show information on team 5667, the Robominers
    """

    @toa.command()
    @bot_has_permissions(embed_links=True)
    async def team(self, ctx, team_num: int):
        """Get information on an FTC team by number."""
        team_data = await self.parser.req("team/" + str(team_num))
        # TOA's rookie year listing is :b:roke, so we have to fix it ourselves
        # This is a _nasty_ hack
        data = self._teams.get(team_num, {
            'rookie_year': 2017,
            'seasons': [{
                'website': 'n/a',
            }]
        })
        last_season = data['seasons'][0]
        team_data.rookie_year = data['rookie_year']

        if team_data.error:
            if team_num not in self._teams:
                # rip
                await ctx.send("This team does not have any data on it yet, or it does not exist!")
                return
            team_data._update(last_season)
            team_data.team_name_short = last_season['name']

        # many team entries lack a valid url
        website = (team_data.website or last_season['website']).strip()
        if website and not (website.startswith("http://") or website.startswith("https://")):
            website = "http://" + website
        e = discord.Embed(color=embed_color)
        e.set_author(name='FIRST® Tech Challenge Team {}'.format(team_num),
                     url='https://www.theorangealliance.org/teams/{}'.format(team_num),
                     icon_url='https://cdn.discordapp.com/icons/342152047753166859/de4d258c0cab5bee0b04d406172ec585.jpg')
        e.add_field(name='Name', value=team_data.team_name_short)
        e.add_field(name='Rookie Year', value=team_data.rookie_year)
        e.add_field(name='Location', value=', '.join((team_data.city, team_data.state_prov, team_data.country)))
        e.add_field(name='Website', value=website or 'n/a')
        e.add_field(name='Team Info Page', value='https://www.theorangealliance.org/teams/{}'.format(team_num))
        e.set_footer(text='Triggered by ' + ctx.author.display_name)
        await ctx.send(embed=e)

    team.example_usage = """
    `{prefix}toa team 12670` - show information on team 12670, Eclipse
    """


def setup(bot):
    bot.add_cog(TOA(bot))
