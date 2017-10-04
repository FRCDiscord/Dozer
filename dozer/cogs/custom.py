import tbapi
import discord
from ._utils import *

blurple = discord.Color.blurple()

class Custom(Cog):
	@command()
	async def rip(self,ctx):
		"""Rest in Piece"""
		await ctx.send('RIP http://worldartsme.com/images/tombstone-clipart-1.jpg')

	@command()
	async def lol(self,ctx):
		"""Laugh out Loud"""
		await ctx.send('LOL')
		
	@command()
	async def doyouhavecustom (self,ctx):
		"""This is for checking if an instance of Dozer has this command."""
		await ctx.send('YES. This Dozer has custom!')
	@command()
	async def tba (self,ctx,task,teamnum):
		"""Retrieve information about this guild."""
		parser = tbapi.TBAParser('3572', 'Dozer', 'Alpha 0.1')
		teamdata = parser.get_team('frc' + teamnum)
		if task == team:
			guild = ctx.guild
			e = discord.Embed(color=blurple)
			e.add_field(name='Team Name', value=teamdata.nickname)
			e.add_field(name='Sponsors', value=teamdata.name)
			e.add_field(name='Team Number', value=teamdata.number)
			e.add_field(name='Team Location', value=teamdata.location)
			e.add_field(name='Rookie Year', value=teamdata.rookie_year)
			e.add_field(name='Team Motto', value=teamdata.motto)
			e.add_field(name='Team Website', value=teamdata.website)
			e.add_field(name='TBA Page', value='https://www.thebluealliance.com/team/' + teamnum)
			await ctx.send(embed=e)
		if task == awards:
			await ctx.send('Awards' + teamnum)
def setup(bot):
	bot.add_cog(Custom(bot))
