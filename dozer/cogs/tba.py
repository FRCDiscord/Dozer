"""A series of commands that talk to The Blue Alliance."""
import datetime
from datetime import timedelta

import discord
from discord.ext.commands import BadArgument
import googlemaps
import tbapi
from geopy.geocoders import Nominatim

from ._utils import *

blurple = discord.Color.blurple()


class TBA(Cog):
    """Commands that talk to The Blue Alliance"""
    def __init__(self, bot):
        super().__init__(bot)
        tba_config = bot.config['tba']
        self.gmaps_key = bot.config['gmaps_key']
        self.parser = tbapi.TBAParser(tba_config['key'], cache=False)

    @group(invoke_without_command=True)
    async def tba(self, ctx, team_num: int):
        """
        Get FRC-related information from The Blue Alliance.
        If no subcommand is specified, the `team` subcommand is inferred, and the argument is taken as a team number.
        """
        await self.team.callback(self, ctx, team_num)

    tba.example_usage = """
    `{prefix}tba 5052` - show information on team 5052, the RoboLobos
    """

    @tba.command()
    @bot_has_permissions(embed_links=True)
    async def status(self, ctx):
        """Get information from the TBA API Status."""
        status_data = self.parser.get_status()
        e = discord.Embed(color=blurple)
        e.set_author(name='The Blue Allaiance API Diagnostic',
             url='https://www.thebluealliance.com/apidocs',
             icon_url='https://www.thebluealliance.com/icons/favicon-32x32.png')
        e.add_field(name='Current Season', value=status_data.current_season)
        e.add_field(name='Max Season', value=status_data.max_season)
        e.add_field(name='Datafeed Down', value=status_data.is_datafeed_down)
        e.set_footer(text='Triggered by ' + ctx.author.display_name + '. Powered By The Blue Alliance.')
        await ctx.send(embed=e)

    status.example_usage = """
    `{prefix}tba status` - Show Information from the TBA API status.
    """

    @tba.command()
    @bot_has_permissions(embed_links=True)
    async def team(self, ctx, team_num: int):
        """Get information on an FRC team by number."""
        team_data = self.parser.get_team(team_num)
        try:
            getattr(team_data, "Errors")
        except tbapi.InvalidKeyError:
            e = discord.Embed(color=blurple)
            e.set_author(name='FIRST® Robotics Competition Team {}'.format(team_num),
                url='https://www.thebluealliance.com/team/{}'.format(team_num),
                icon_url='https://frcavatars.herokuapp.com/get_image?team={}'.format(team_num))
            e.add_field(name='Name', value=team_data.nickname)
            e.add_field(name='Rookie Year', value=team_data.rookie_year)
            e.add_field(name='Home Championship', value="2011 thru 2017: " + team_data.home_championship['2017'] + "\n 2018 thru 2020: " + team_data.home_championship['2018'])
            e.add_field(name='Location',
                        value='{0.city}, {0.state_prov} {0.postal_code}, {0.country}'.format(team_data))
            e.add_field(name='Website', value=team_data.website)
            e.add_field(name='TBA Link', value='https://www.thebluealliance.com/team/{}'.format(team_num))
            e.add_field(name='Sponsors', value=team_data.name)
            e.set_footer(text='Triggered by ' + ctx.author.display_name + '. Powered By The Blue Alliance.')
            await ctx.send(embed=e)
        else:
            raise BadArgument("Couldn't find data for team {}".format(team_num))

    team.example_usage = """
    `{prefix}tba team 4131` - show information on team 4131, the Iron Patriots
    """
    
    @tba.command()
    @bot_has_permissions(embed_links=True)
    async def event(self, ctx, event_key):
        """Get information on an FRC event by event key (year+eventcode, ex. 2019mimus)."""
        event_data = self.parser.get_event(event_key)
        try:
            getattr(event_data, "Errors")
        except tbapi.InvalidKeyError:
            e = discord.Embed(color=blurple)
            e.set_author(name=str(event_data.year) + ' ' + event_data.name,
                url='https://www.thebluealliance.com/event/{}'.format(event_key),
                icon_url='https://www.thebluealliance.com/icons/favicon-32x32.png')
            e.add_field(name='Event Type', value=event_data.event_type_string)
            e.add_field(name='Google Maps URL', value=event_data.gmaps_url)
            e.add_field(name='Location Name', value=event_data.location_name)
            e.add_field(name='Start Date', value=event_data.start_date)
            e.add_field(name='End Date', value=event_data.end_date)
            e.add_field(name='Event Timezone', value=event_data.timezone)
            e.add_field(name='Event Website', value=event_data.website)
            e.add_field(name='TBA Link', value='https://thebluealliance.com/event/{}'.format(event_key))
            e.set_footer(text='Triggered by ' + ctx.author.display_name + '. Powered By The Blue Alliance.')
            await ctx.send(embed=e)
        else:
            raise BadArgument("Couldn't find data for event key {}".format(event_key))

    event.example_usage = """
    `{prefix}tba event 2019mimus` - show information on the 2019 FIM District Muskegon Event.
    """

    @tba.command()
    async def raw(self, ctx, team_num: int):
        """
        Get raw TBA API output for a team.
        This command is really only useful for development.
        """
        team_data = self.parser.get_team(team_num)
        try:
            getattr(team_data, "Errors")
        except tbapi.InvalidKeyError:
            e = discord.Embed(color=blurple)
            e.set_author(name='FIRST® Robotics Competition Team {}'.format(team_num),
                url='https://www.thebluealliance.com/team/{}'.format(team_num),
                icon_url='https://frcavatars.herokuapp.com/get_image?team={}'.format(team_num))
            e.add_field(name='Raw Data', value=team_data.flatten())
            e.set_footer(text='Triggered by ' + ctx.author.display_name + '. Powered By The Blue Alliance.')
            await ctx.send(embed=e)
        else:
            raise BadArgument('Team {} does not exist.'.format(team_num))

    raw.example_usage = """
    `{prefix}tba raw 4150` - show raw information on team 4150, FRobotics
    """

    @command()
    async def timezone(self, ctx, team_num: int):
        """
        Get the timezone of a team based on the team number.
        """

        team_data = self.parser.get_team(team_num)
        try:
            getattr(team_data, "Errors")
        except tbapi.InvalidKeyError:
            location = '{0.city}, {0.state_prov} {0.country}'.format(team_data)
            gmaps = googlemaps.Client(key=self.gmaps_key)
            geolocator = Nominatim()
            geolocation = geolocator.geocode(location)
            timezone = gmaps.timezone(location="{}, {}".format(geolocation.latitude, geolocation.longitude),
                                      language="json")
            utc_offset = int(timezone["rawOffset"]) / 3600
            if timezone["dstOffset"] == 3600:
                utc_offset += 1
            utc_timedelta = timedelta(hours=utc_offset)
            currentUTCTime = datetime.datetime.utcnow()
            currentTime = currentUTCTime + utc_timedelta
            current_hour = currentTime.hour
            current_hour_original = current_hour
            dayTime = "AM"
            if current_hour > 12:
                current_hour -= 12
                dayTime = "PM"
            elif current_hour == 12:
                dayTime = "PM"
            elif current_hour == 0:
                current_hour = 12
                dayTime = "AM"
            current_minute = currentTime.minute
            if current_minute < 10:
                current_minute = "0{}".format(current_minute)
            current_second = currentTime.second
            if current_second < 10:
                current_second = "0{}".format(current_second)
            await ctx.send(
                "Timezone: {0} UTC{1:+g} \nCurrent Time: {2}:{3}:{4} {5} ({6}:{3}:{4})".format(
                    timezone["timeZoneName"], utc_offset, current_hour, current_minute, current_second, dayTime, current_hour_original))
        else:
            raise BadArgument('Team {} does not exist.'.format(team_num))

    timezone.example_usage = """
    `{prefix}timezone 3572` - show the local time of team 3572, Wavelength
    """


def setup(bot):
    """Adds the TBA cog to the bot"""
    bot.add_cog(TBA(bot))
