import tbapi
import discord
from ._utils import *
from discord.ext.commands import BadArgument, Group, bot_has_permissions, has_permissions

blurple = discord.Color.blurple()

class TBA(Cog):
	def __init__(self, bot):
		super().__init__(bot)
		tba_config = bot.config['tba']
		self.parser = tbapi.TBAParser(tba_config['team'], tba_config['application'], tba_config['version'])
	
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
		team_data = self.parser.get_team('frc{}'.format(team_num))
		e = discord.Embed(color=blurple)
		e.set_author(name='FIRST® Robotics Competition Team {}'.format(team_num), url='https://www.thebluealliance.com/team/{}'.format(team_num), icon_url='http://i.imgur.com/V8nrobr.png')
		e.add_field(name='Name', value=team_data.nickname)
		e.add_field(name='Rookie Year', value=team_data.rookie_year)
		e.add_field(name='Location', value=team_data.location)
		e.add_field(name='Website', value=team_data.website)
		e.add_field(name='Motto', value=team_data.motto)
		e.set_footer(text='Triggered by ' + ctx.author.display_name)
		await ctx.send(embed=e)
	
	team.example_usage = """
	`{prefix}tba team 4131` - show information on team 4131, the Iron Patriots
	"""
	
	@tba.command()
	async def raw(self, ctx, team_num: int):
		"""
		Get raw TBA API output for a team.
		This command is really only useful for development.
		"""
		team_data = self.parser.get_team('frc{}'.format(team_num))
		await ctx.send(team_data.raw)
	
	raw.example_usage = """
	`{prefix}tba raw 4150` - show raw information on team 4150, FRobotics
	"""
		 
def setup(bot):
	bot.add_cog(TBA(bot))