"""Provides commands that pull information from The Orange Alliance, an FTC info API."""

import json
from asyncio import sleep
from datetime import datetime
from urllib.parse import urljoin, urlencode
import base64

import aiohttp
import async_timeout
import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import escape_markdown

from dozer.context import DozerContext
from ._utils import *

embed_color = discord.Color(0xed791e)

__all__ = ['FTCEventsClient', 'FTCInfo', 'setup']

def get_none_strip(s, key):
    """Ensures that a get always returns a stripped string.""" 
    return str(s.get(key, "") or "").strip()

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
        self.headers: dict = {'Authorization': 'Basic ' + base64.b64encode(f"{username}:{token}".encode()).decode()}

    async def req(self, endpoint, season=None):
        """Make an async request at the specified endpoint, waiting to let the ratelimit cool off."""

        if season is None:
            season = FTCEventsClient.get_season()

        if self.ratelimit:
            # this will delay a request to avoid the ratelimit
            now = datetime.now()
            diff = (now - self.last_req).total_seconds()
            self.last_req = now
            if diff < 0.5:  # have a 200 ms fudge factor
                await sleep(0.5 - diff)
        tries = 0
        while True:
            try:
                return await self.http.get(urljoin(f"{self.base}/{season}/", endpoint), headers=self.headers)
            except aiohttp.ClientError:
                tries += 1
                if tries > 3:
                    raise
    
    async def reqjson(self, endpoint, season=None, on_400=None, on_other=None):
        """Reqjson."""
        res = await self.req(endpoint, season=season)
        async with res:
            if res.status == 400 and on_400:
                await on_400(res)
                return None
            elif res.status >= 400:
                if on_other:
                    await on_other(res)
                return None
            return await res.json(content_type=None)


    @staticmethod
    def get_season():
        """Fetches the current season, based on typical kickoff date."""
        today = datetime.today()
        year = today.year
        # ftc kickoff is always the 2nd saturday of september
        kickoff = [d for d in [datetime(year=year, month=9, day=i) for i in range(8, 15)] if d.weekday() == 5][
            0]
        if kickoff > today:
            return today.year - 1
        return today.year
    
    @staticmethod
    def date_parse(date_str):
        """Takes in date strings from FTC-Events and parses them into a datetime.datetime"""
        return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S")

    @staticmethod
    def team_fmt(team, team_num=None):
        """TBA-formats a team."""
        t = str(team['teamNumber'])
        if team['surrogate']:
            # indicate surrogate status by italicizing them
            t = f"*{t}*"
        if team['teamNumber'] == team_num:
            # underline the team
            t = f"__{t}__"
        if team['noShow'] or team['dq']:
            # cross out the team
            t = f"~~{t}~~"
        return t

    @staticmethod
    def get_url_for_match(szn: int, ecode: str, match: dict):
        """Produces a URL for a match dict + some other info."""
        base = f"https://ftc-events.firstinspires.org/{szn}/{ecode}/"
        if match['tournamentLevel'] == "SEMIFINAL":
            return base + f"semifinal/{match['series']}/{match['matchNumber']}"
        if match['tournamentLevel'] == "FINAL":
            return base + f"final/{match['series']}/{match['matchNumber']}"
        else:
            return base + f"qualifications/{match['matchNumber']}"

    @staticmethod
    def add_schedule_to_embed(embed: discord.Embed, schedule: list, team_num: int, szn: int, ecode: str):
        """Adds a schedule to an embed conditioned on a team number."""
        for m in schedule:
            played = m['scoreRedFinal'] is not None
            red_alliance = []
            blu_alliance = []
            team_alliance = None
            for team in m['teams']:
                alliance = "blue"
                if (team['station'] or "").startswith("Red"):
                    alliance = "red"
                    red_alliance.append(team)
                else:
                    blu_alliance.append(team)
                team_alliance = team_alliance or (team['teamNumber'] == team_num and alliance)

            if not team_alliance: 
                continue
            red_fmt = []
            blu_fmt = []
            for team in red_alliance:
                red_fmt.append(FTCEventsClient.team_fmt(team, team_num=team_num))
            for team in blu_alliance:
                blu_fmt.append(FTCEventsClient.team_fmt(team, team_num=team_num))
            
            red_fmt = ", ".join(red_fmt)
            blu_fmt = ", ".join(blu_fmt)
            red_score = m['scoreRedFinal'] or "0"
            blu_score = m['scoreBlueFinal'] or "0"

            wincode = "⬜"
            if m['redWins']:
                red_fmt = f"**{red_fmt}**"
                red_score = f"**{red_score}**"
                wincode = "🟥"
            if m['blueWins']:
                blu_fmt = f"**{blu_fmt}**"
                blu_score = f"**{blu_score}**"
                wincode = "🟦"
            
            field_desc = f"{red_fmt} vs. {blu_fmt}"

            if not played: 
                field_title = f"{m['description']}: unplayed"
                embed.add_field(name=field_title, value=field_desc, inline=False)
                continue
            else:
                if (m['redWins'] and team_alliance == "red") or (m['blueWins'] and team_alliance == 'blue'):
                    field_title = f"{m['description']}: Win 🟨"
                elif not m['redWins'] and not m['blueWins']:
                    field_title = f"{m['description']}: Tie ⬜"
                else:
                    field_title = f"{m['description']}: Loss 🇱"

            if team_alliance == "red":
                red_score = f"__{red_score}__"
            else:
                blu_score = f"__{blu_score}__"

            field_desc = field_desc + f" {wincode} {red_score}-{blu_score}"
            embed.add_field(name=field_title, value=f"[{field_desc}]({FTCEventsClient.get_url_for_match(szn, ecode, m)})",
                            inline=False)
            
class ScoutParser:
    """
    A class to make async requests to FTCScout.
    """

    def __init__(self, aiohttp_session, base_url: str = "https://api.ftcscout.org/rest/v1/",
                 ratelimit: bool = True):
        self.last_req = datetime.now()
        self.ratelimit = ratelimit
        self.base = base_url
        self.http = aiohttp_session
        self.headers = {
            'Content-Type': 'application/json'
        }

    async def req(self, endpoint):
        """Make an async request at the specified endpoint, waiting to let the ratelimit cool off.
        For FTCDashboard ratelimit probably unnecessary, but polite"""
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
                async with async_timeout.timeout(5) as _:
                    return await self.http.get(urljoin(self.base, endpoint),
                                               headers=self.headers)
            except aiohttp.ClientError:
                tries += 1
                if tries > 3:
                    raise

class FTCInfo(Cog):
    """Commands relating specifically to fetching information about FTC teams."""

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self.http_session = bot.add_aiohttp_ses(aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(5)))
        self.ftcevents = FTCEventsClient(bot.config['ftc-events']['username'], bot.config['ftc-events']['token'],
                                         self.http_session)
        self.scparser = ScoutParser(self.http_session)

    @group(invoke_without_command=True, aliases=["ftcteam", "toa", "toateam", "ftcteaminfo"])
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
    @app_commands.describe(team_num = "The number of the team you're interested in getting info")
    async def team(self, ctx: DozerContext, team_num: int):
        """Get information on an FTC team by number."""
        if team_num < 1:
            await ctx.send("Invalid team number specified!")
        res = await self.ftcevents.req("teams?" + urlencode({'teamNumber': str(team_num)}))
        sres = await self.scparser.req(f"teams/{team_num}/quick-stats")
        async with res, sres:
            if res.status == 400:
                await ctx.send("This team either did not compete this season, or it does not exist!")
                return
            team_data = await res.json(content_type=None)
            if not team_data:
                await ctx.send(f"FTC-Events returned nothing on request with HTTP response code {res.status}.")
                return
            team_data = team_data['teams'][0]

            # many team entries lack a valid url
            website = get_none_strip(team_data, 'website')
            if website and not (website.startswith("http://") or website.startswith("https://")):
                website = "http://" + website

            e = discord.Embed(color=embed_color, 
                              title=f'FIRST® Tech Challenge Team {team_num}',
                              url=f"https://ftc-events.firstinspires.org/{FTCEventsClient.get_season()}/team/{team_num}")
            e.add_field(name='Name', value=get_none_strip(team_data, 'nameShort') or "_ _")
            e.add_field(name='Rookie Year', value=get_none_strip(team_data, 'rookieYear') or "Unknown")
            e.add_field(name='Location',
                        value=', '.join((team_data['city'], team_data['stateProv'], team_data['country'])) or "Unknown")
            e.add_field(name='Org/Sponsors', value=team_data.get('nameFull', "").strip() or "_ _")
            e.add_field(name='Website', value=website or 'n/a')
            e.add_field(name='FTCScout Page', value=f'https://ftcscout.org/teams/{team_num}')

            if sres.status != 404:
                team_stats = await sres.json(content_type = None)
                e.add_field(name = 'Total OPR',
                            value = f"{team_stats['tot']['value']:.0f}, rank #{team_stats['tot']['rank']:.0f}")
                e.add_field(name = 'Auto OPR',
                            value = f"{team_stats['auto']['value']:.0f}, rank #{team_stats['auto']['rank']:.0f}")
                e.add_field(name = 'Teleop OPR',
                            value = f"{team_stats['dc']['value']:.0f}, rank #{team_stats['dc']['rank']:.0f}")
                e.add_field(name = 'Endgame OPR',
                            value = f"{team_stats['eg']['value']:.0f}, rank #{team_stats['eg']['rank']:.0f}")

            await ctx.send(embed=e)

    team.example_usage = """
    `{prefix}ftc team 7244` - show information on team 7244, Out of the Box Robotics
    """

    @ftc.command()
    @bot_has_permissions(embed_links=True)
    @app_commands.describe(team_num = "The number of the team you're interested in getting matches for", 
                           event_name = "The official name of the event")
    async def matches(self, ctx: DozerContext, team_num: int, event_name: str = "latest"):
        """Get a match schedule, defaulting to the latest listed event on FTC-Events"""
        szn = FTCEventsClient.get_season()
        events = await self.ftcevents.reqjson("events?" + urlencode({'teamNumber': str(team_num)}),
                                              on_400=lambda r: ctx.send(
                                                  "This team either did not compete this season, or it does not exist!"),
                                              on_other=lambda r: ctx.send(
                                                  f"FTC-Events returned an HTTP error status of: {r.status}. Something is broken."))
        if events is None:
            return
        
        events = events['events']
        if len(events) == 0:
            await ctx.send("This team did not attend any events this season!")
            return

        event = None
        if event_name == "latest":
            # sort all events by date start
            events = sorted(events, key=lambda e: FTCEventsClient.date_parse(e['dateStart']), reverse=True)
            event = events[0]

            divisions = {}
            # the event that should be used is the latest unpublished event. divisioned events are considered 1 event.

            # event division filter:
            for e in events:
                if e['divisionCode']:
                    if e['divisionCode'] not in divisions:
                        divisions[e['divisionCode']] = [e['code']]
                    else:
                        divisions[e['divisionCode']].append(e['code'])
            
            for e in events:
                if e['code'] in divisions:
                    continue
                event = e
                break
            
        else:
            for e in events:
                if e['code'] == event_name:
                    event = e
            if event is None:
                await ctx.send(f"Team {team_num} did not attend {event_name}!")
                return
        # 
        event_url = f"https://ftc-events.firstinspires.org/{szn}/{event['code']}"
        
        # fetch the rankings
        rank_res = await self.ftcevents.reqjson(f"rankings/{event['code']}?" + urlencode({'teamNumber': str(team_num)}),
                                                on_400=lambda r: ctx.send(
                                                    f"This team somehow competed at an event ({event_url}) that it is "
                                                    f"not ranked in -- did it no show?"),
                                                on_other=lambda r: ctx.send(
                                                    f"FTC-Events returned an HTTP error status of: {r.status}. "
                                                    f"Something is broken.")
                                                )
        if rank_res is None:
            return
        rank_res = rank_res['Rankings']

        if not rank_res:
            rank = None
            description = "_No rankings are available for this event._"
        else:
            rank = rank_res[0]
            description = f"Rank **{rank['rank']}**\nWLT **{rank['wins']}-{rank['losses']}-{rank['ties']}**\n" \
                          f"QP/TBP1 **{rank['sortOrder1']} / {rank['sortOrder2']}** "

        embed = discord.Embed(color=embed_color, title=f"FTC Team {team_num} @ {event['name']}", url=event_url,
                              description=description)
        has_matches_at_all = False

        # fetch the quals match schedule
        req = await self.ftcevents.reqjson(f"schedule/{event['code']}/qual/hybrid",
                                           on_other=lambda r: ctx.send(
                                               f"FTC-Events returned an HTTP error status of: {req.status}. Something is broken."))
        if req is None:
            return
        res = req['schedule']
        has_matches_at_all = has_matches_at_all or bool(res)
        FTCEventsClient.add_schedule_to_embed(embed, res, team_num, szn, event['code'])

        # fetch the playoffs match schedule
        req = await self.ftcevents.reqjson(f"schedule/{event['code']}/playoff/hybrid",
                                           on_other=lambda r: ctx.send(
                                               f"FTC-Events returned an HTTP error status of: {req.status}. Something is broken."))
        if req is None:
            return
        res = req['schedule']
        has_matches_at_all = has_matches_at_all or bool(res)
        FTCEventsClient.add_schedule_to_embed(embed, res, team_num, szn, event['code'])
        
        if not has_matches_at_all:
            embed.description = "_No match schedule is available yet._"
            
        await ctx.send(embed=embed)

    matches.example_usage = """
    `{prefix}ftc matches 16377` - show matches for the latest event by team 16377, Spicy Ketchup
    `{prefix}ftc matches 8393 USPACMP` - show matches for the Pennsylvania championship by team 8393, BrainSTEM
    """



async def setup(bot):
    """Adds the FTC information cog to the bot."""
    await bot.add_cog(FTCInfo(bot))
