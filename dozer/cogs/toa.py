import discord
import datetime
from ._utils import *
from ._toa import *
from discord.ext import commands
from discord.ext.commands import BadArgument, Group, bot_has_permissions, has_permissions
from datetime import timedelta

embed_color = discord.Color(0xff9800)
class TOA(Cog):
	def __init__(self, bot):
		super().__init__(bot)
		self.parser = TOAParser(bot.config['toa_key'])
	
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
		if team_data.error:
			await ctx.send("This team does not have any data on it yet, or it does not exist!")
			return

		e = discord.Embed(color=embed_color)
		e.set_author(name='FIRST® Tech Challenge Team {}'.format(team_num), url='https://www.theorangealliance.org/teams/'.format(team_num), icon_url='https://cdn.discordapp.com/icons/342152047753166859/de4d258c0cab5bee0b04d406172ec585.jpg')
		e.add_field(name='Name', value=team_data.team_name_short)
		e.add_field(name='Rookie Year', value=team_data.rookie_year)
		e.add_field(name='Location', value=', '.join((team_data.city, team_data.state_prov, team_data.country)))
		e.add_field(name='Website', value=team_data.website or "n/a")
		e.add_field(name='FTCRoot Page', value='http://www.ftcroot.com/teams/{}'.format(team_num))
		e.set_footer(text='Triggered by ' + ctx.author.display_name)
		await ctx.send(embed=e)

	
	team.example_usage = """
	`{prefix}toa team 12670` - show information on team 12670, Eclipse
	"""

def setup(bot):
	bot.add_cog(TOA(bot))
