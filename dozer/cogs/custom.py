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
		if task == team:
		team = parser.get_team('frc' + teamnum)
		guild = ctx.guild
		e = discord.Embed(color=blurple)
		e.add_field(name='Team Name', value=team.nickname)
		e.add_field(name='Sponsors', value=team.name)
		e.add_field(name='Team Number', value=team.number)
		e.add_field(name='Team Location', value=team.location)
		e.add_field(name='Rookie Year', value=team.rookie_year)
		e.add_field(name='Team Motto', value=team.motto)
		e.add_field(name='Team Website', value=team.website)
		e.add_field(name='TBA Page', value='https://www.thebluealliance.com/team/' + teamnum)
		await ctx.send(embed=e)
		if task == awards:
		await ctx.send('Awards' + teamnum)
def setup(bot):
	bot.add_cog(Custom(bot))
