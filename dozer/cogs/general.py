from discord.ext.commands import has_permissions
import discord
from ._utils import *
import discord as Discordpy

class General(Cog):
	@command()
	async def ping(self, ctx):
		"""Check the bot is online, and calculate its response time."""
		if ctx.guild is None:
			location = 'DMs'
		else:
			location = 'the **%s** server' % ctx.guild.name
		response = await ctx.send('Pong! We\'re in %s.' % location)
		delay = response.created_at - ctx.message.created_at
		await response.edit(content=response.content + '\nTook %d ms to respond.' % (delay.seconds * 1000 + delay.microseconds // 1000))
	@has_permissions(change_nickname=True)
	@command()
	async def nick(self, ctx, *, nicktochangeto):
		await discord.Member.edit(ctx.author, nick=nicktochangeto)
def setup(bot):
	bot.add_cog(General(bot))
