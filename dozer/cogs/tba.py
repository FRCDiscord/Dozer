import tbapi
import discord
from ._utils import *

blurple = discord.Color.blurple()

class tba(Cog):
	def _init_(self):
		parser = tbapi.TBAParser('0000', 'Dozer', 'Beta 0.7')
	@command()
	async def tba (self,ctx,task,teamnum):
		"""Pulls Team Data from TBA. Subcommand Team: Pulls team data."""
		teamdata = parser.get_team('frc' + teamnum)
		if task == 'team':
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
		if task == 'raw':
			await ctx.send(teamdata.raw)

	
def setup(bot):
	bot.add_cog(tba(bot))
