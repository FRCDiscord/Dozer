import tbapi
from ._utils import *

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
	async def tbateam (self,ctx,argument):
		parser = tbapi.TBAParser('3572', 'Dozer', 'Alpha 0.1')
		team = parser.get_team('frc' + argument)
		await ctx.send('Sponsors: ' + team.name)
		await ctx.send('Team Name: ' + team.nickname)
		await ctx.send('Team Number: ' + argument)
		await ctx.send('Team Location: ' + team.location)
		await ctx.send('Team Rookie Year: ' + team.rookie_year)
		await ctx.send('Team Motto: ' + team.motto)
		await ctx.send(team.website)
def setup(bot):
	bot.add_cog(Custom(bot))
