import tbapi
import discord
from ._utils import *

blurple = discord.Color.blurple()

class tba(Cog):
	def _init_(self):
		parser = tbapi.TBAParser('0000', 'Dozer', 'Beta 0.7')
	
	@group(invoke_without_command=True)
	async def tba(self, ctx, teamnum):
		"""Pulls data on FRC teams from The Blue Alliance."""
		teamdata = parser.get_team('frc' + teamnum)
		tba.example_usage = """
	`{prefix}tba team <team-number>` - Pulls information about an FRC team.
	`{prefix}tba raw <team-number>` - Pulls raw data for an FRC Team.
	"""
	@tba.command()
	async def team(self, ctx, teamnum):
			guild = ctx.guild
			e = discord.Embed(color=blurple)
			e.add_field(name='Team Name', value=teamdata.nickname)
			e.add_field(name='Sponsors', value=teamdata.name)
			e.add_field(name='Team Number', value=teamdata.number)
			e.add_field(name='Team Key', value=teamdata.key)
			e.add_field(name='Team Location', value=teamdata.location)
			e.add_field(name='Rookie Year', value=teamdata.rookie_year)
			e.add_field(name='Team Motto', value=teamdata.motto)
			e.add_field(name='Team Website', value=teamdata.website)
			e.add_field(name='TBA Page', value='https://www.thebluealliance.com/team/' + teamnum)
			await ctx.send(embed=e)
	
		
def setup(bot):
	bot.add_cog(tba(bot))
