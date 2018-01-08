import tbapi
import discord
import googlemaps
import datetime
from ._utils import *
from discord.ext import commands
from discord.ext.commands import BadArgument, Group, bot_has_permissions, has_permissions
from geopy.geocoders import Nominatim
from datetime import timedelta

blurple = discord.Color.blurple()


class TBA(Cog):
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
	async def team(self, ctx, team_num: int):
		"""Get information on an FRC team by number."""
		team_data = self.parser.get_team(team_num)
		try:
			getattr(team_data, "Errors")
		except tbapi.InvalidKeyError:
			e = discord.Embed(color=blurple)
			e.set_author(name='FIRST® Robotics Competition Team {}'.format(team_num), url='https://www.thebluealliance.com/team/{}'.format(team_num), icon_url='http://i.imgur.com/V8nrobr.png')
			e.add_field(name='Name', value=team_data.nickname)
			e.add_field(name='Rookie Year', value=team_data.rookie_year)
			e.add_field(name='Location', value='{0.city}, {0.state_prov} {0.postal_code}, {0.country}'.format(team_data))
			e.add_field(name='Website', value=team_data.website)
			e.add_field(name='TBA Link', value='https://www.thebluealliance.com/team/{}'.format(team_num))
			e.set_footer(text='Triggered by ' + ctx.author.display_name)
			await ctx.send(embed=e)
		else:
			raise BadArgument("Couldn't find data for team {}".format(team_num))

	team.example_usage = """
	`{prefix}tba team 4131` - show information on team 4131, the Iron Patriots
	"""

	@tba.command()
	async def raw(self, ctx, team_num: int):
		"""
		Get raw TBA API output for a team.
		This command is really only useful for development.
		"""
		try:
			team_data = self.parser.get_team(team_num)
		except KeyError:
			raise BadArgument('Team {} does not exist.'.format(team_num))
		e = discord.Embed(color=blurple)
		e.set_author(name='FIRST® Robotics Competition Team {}'.format(team_num), url='https://www.thebluealliance.com/team/{}'.format(team_num), icon_url='http://i.imgur.com/V8nrobr.png')
		e.add_field(name='Raw Data', value=team_data.flatten())
		e.set_footer(text='Triggered by ' + ctx.author.display_name)
		await ctx.send(embed=e)

	raw.example_usage = """
	`{prefix}tba raw 4150` - show raw information on team 4150, FRobotics
	"""

	@command()
	async def timezone(self, ctx, team_num: int):
		"""
		Get the timezone of a team based on the team number.
		"""
		try:
			team_data = self.parser.get_team(team_num)
		except KeyError:
			raise BadArgument('Team {} does not exist.'.format(team_num))
		location = '{0.city}, {0.state_prov} {0.postal_code}, {0.country}'.format(team_data)
		gmaps = googlemaps.Client(key=self.gmaps_key)
		geolocator = Nominatim()
		geolocation = geolocator.geocode(location)
		timezone = gmaps.timezone(location="{}, {}".format(geolocation.latitude, geolocation.longitude), language="json")
		utc_offset = int(timezone["rawOffset"])/3600
		if timezone["dstOffset"] == 3600:
			utc_offset += 1
		utc_timedelta = timedelta(hours = utc_offset)
		currentUTCTime = datetime.datetime.utcnow()
		currentTime = currentUTCTime+utc_timedelta
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
		await ctx.send("Timezone: {0} UTC{1:+g} \nCurrent Time: {2}:{3}:{4} {5} ({6}:{3}:{4})".format(timezone["timeZoneName"], utc_offset, current_hour, current_minute, current_second, dayTime, current_hour_original)) 
					
	timezone.example_usage = """
	`{prefix}timezone 3572` - show the local time of team 3572, Wavelength
	"""
def setup(bot):
	bot.add_cog(TBA(bot))
