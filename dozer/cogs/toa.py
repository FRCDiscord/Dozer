"""Provides commands that pull information from The Orange Alliance, an FTC info API."""

import json
from asyncio import sleep
from datetime import datetime
from urllib.parse import urljoin

import aiohttp
import async_timeout
import discord
from discord.ext import commands
from discord.utils import escape_markdown

from dozer.context import DozerContext
from ._utils import *

embed_color = discord.Color(0xf89808)


class TOAParser:
    """
    A class to make async requests to The Orange Alliance.
    """

    def __init__(self, api_key: str, aiohttp_session, base_url: str = "https://theorangealliance.org/api/",
                 app_name: str = "Dozer",
                 ratelimit: bool = True):
        self.last_req = datetime.now()
        self.ratelimit = ratelimit
        self.base = base_url
        self.http = aiohttp_session
        self.headers = {
            'X-Application-Origin': app_name,
            'X-TOA-Key': api_key,
            'Content-Type': 'application/json'
        }

    async def req(self, endpoint):
        """Make an async request at the specified endpoint, waiting to let the ratelimit cool off."""
        if self.ratelimit:
            # this will delay a request to avoid the ratelimit
            now = datetime.now()
            diff = (now - self.last_req).total_seconds()
            self.last_req = now
            if diff < 2.2:  # have a 200 ms fudge factor
                await sleep(2.2 - diff)
        tries = 0
        while True:
            try:
                async with async_timeout.timeout(5) as _, self.http.get(urljoin(self.base, endpoint),
                                                                        headers=self.headers) as response:
                    if response.status == 404:
                        return "[]"
                    return await response.text()
            except aiohttp.ClientError:
                tries += 1
                if tries > 3:
                    raise


class TOA(Cog):
    """TOA commands"""

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self.http_session = bot.add_aiohttp_ses(aiohttp.ClientSession())
        self.parser = TOAParser(bot.config['toa']['key'], self.http_session, app_name=bot.config['toa']['app_name'])

    @group(invoke_without_command=True)
    async def toa(self, ctx: DozerContext, team_num: int):
        """
        Get FTC-related information from The Orange Alliance.
        If no subcommand is specified, the `team` subcommand is inferred, and the argument is taken as a team number.
        """
        await self.team.callback(self, ctx, team_num)  # This works but Pylint throws an error

    toa.example_usage = """
    `{prefix}toa 5667` - show information on team 5667, Robominers
    """

    @toa.command()
    @bot_has_permissions(embed_links=True)
    async def team(self, ctx: DozerContext, team_num: int):
        """Get information on an FTC team by number."""
        res = json.loads(await self.parser.req("team/" + str(team_num)))
        if len(res) == 0:
            await ctx.send("This team does not have any data on it yet, or it does not exist!")
            return
        team_data = res[0]

        e = discord.Embed(color=embed_color)
        e.set_author(name=f'FIRST® Tech Challenge Team {team_num}',
                     url=f'https://theorangealliance.org/teams/{team_num}',
                     icon_url='https://theorangealliance.org/assets/imgs/favicon.png?v=1')
        e.add_field(name='Name', value=team_data['team_name_short'])
        e.add_field(name='Rookie Year', value=team_data['rookie_year'])
        e.add_field(name='Location',
                    value=', '.join((team_data['city'], team_data['state_prov'], team_data['country'])))
        e.add_field(name='Website', value=team_data['website'] or 'n/a')
        e.add_field(name='Team Info Page', value=f'https://theorangealliance.org/teams/{team_data["team_key"]}')
        e.set_footer(text='Triggered by ' + escape_markdown(ctx.author.display_name))
        await ctx.send('', embed=e)

    team.example_usage = """
    `{prefix}toa team 12670` - show information on team 12670, Eclipse
    """


async def setup(bot):
    """Adds the TOA cog to the bot."""
    await bot.add_cog(TOA(bot))
