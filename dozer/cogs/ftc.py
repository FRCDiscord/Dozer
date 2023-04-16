"""Provides commands that pull information from The Orange Alliance, an FTC info API."""

import json
from asyncio import sleep
from datetime import datetime
from urllib.parse import urljoin, urlencode
import base64

import aiohttp
import async_timeout
import discord
from discord.ext import commands
from discord.utils import escape_markdown

from dozer.context import DozerContext
from ._utils import *

embed_color = discord.Color(0xed791e)


class FTCEventsClient:
    """
    A class to make async requests to the FTC-Events API.
    """

    def __init__(self, username: str, token: str, aiohttp_session: aiohttp.ClientSession, base_url: str = "https://ftc-api.firstinspires.org/v2.0",
                 ratelimit: bool = True):
        self.last_req: datetime = datetime.now()
        self.ratelimit: bool = ratelimit
        self.base: str = base_url
        self.http: aiohttp.ClientSession = aiohttp_session
        self.headers: dict = { 'Authorization': 'Basic ' + base64.b64encode(f"{username}:{token}".encode()).decode() }

    async def req(self, endpoint, season=None):
        """Make an async request at the specified endpoint, waiting to let the ratelimit cool off."""

        if season is None:
            season = self.get_season()

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
                return await self.http.get(urljoin(f"{self.base}/{season}/", endpoint), headers=self.headers)
            except aiohttp.ClientError:
                tries += 1
                if tries > 3:
                    raise

    def get_season(self):
        """Fetches the current season, based on typical kickoff date."""
        today = datetime.today()
        year = today.year
        # ftc kickoff is always the 2nd saturday of september
        kickoff = [d for d in [datetime(year=year, month=9, day=i) for i in range(8, 15)] if d.weekday() == 5][0]
        if kickoff > today:
            return today.year - 1
        return today.year



class FTCInfo(Cog):
    """Commands relating specifically to fetching information about FTC teams."""

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self.http_session = bot.add_aiohttp_ses(aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(5)))
        self.ftcevents = FTCEventsClient(bot.config['ftc-events']['username'], bot.config['ftc-events']['token'], self.http_session)

    @group(invoke_without_command=True)
    async def ftc(self, ctx: DozerContext, team_num: int):
        """
        Get information on an FTC team from FTC-Events.
        If no subcommand is specified, the `team` subcommand is inferred, and the argument is taken as a team number.
        """
        await self.team.callback(self, ctx, team_num)  # This works but Pylint throws an error

    ftc.example_usage = """
    `{prefix}ftc 5667` - show information on team 5667, Robominers
    """

    @ftc.command()
    @bot_has_permissions(embed_links=True)
    async def team(self, ctx: DozerContext, team_num: int):
        """Get information on an FTC team by number."""
        if team_num < 1:
            await ctx.send("Invalid team number specified!")
        res = await self.ftcevents.req("teams?" + urlencode({'teamNumber': str(team_num)}))
        async with res:
            print(res.status)
            if res.status == 400:
                await ctx.send("This team either did not compete this season, or it does not exist!")
                return
            team_data = (await res.json(content_type=None))['teams'][0]

            print(team_data)

            # many team entries lack a valid url
            website = (team_data.get('website', "")).strip()
            if website and not (website.startswith("http://") or website.startswith("https://")):
                website = "http://" + website

            e = discord.Embed(color=embed_color, 
                              title=f'FIRST® Tech Challenge Team {team_num}',
                              url=f"https://ftc-events.firstinspires.org/{self.ftcevents.get_season()}/team/{team_num}")
            e.add_field(name='Name', value=team_data.get('nameShort', "").strip() or "_ _")
            e.add_field(name='Rookie Year', value=team_data.get('rookieYear', "Unknown"))
            e.add_field(name='Location',
                        value=', '.join((team_data['city'], team_data['stateProv'], team_data['country'])) or "Unknown")
            e.add_field(name='Org/Sponsors', value=team_data.get('nameFull', "").strip() or "_ _")
            e.add_field(name='Website', value=website or 'n/a')
            await ctx.send(embed=e)

    team.example_usage = """
    `{prefix}ftc team 7244` - show information on team 7244, Out of the Box Robotics
    """


async def setup(bot):
    """Adds the FTC information cog to the bot."""
    await bot.add_cog(FTCInfo(bot))
