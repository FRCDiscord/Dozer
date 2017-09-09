from ._utils import *

class General(Cog):
	@command()
	async def ping(self, ctx):
		"""Check the bot is online, and calculate its response time."""
		response = await ctx.send('Pong! We\'re in the **%s** server.' % ctx.guild.name)
		delay = response.created_at - ctx.message.created_at
		await response.edit(content=response.content + '\nTook %d ms to respond.' % (delay.seconds * 1000 + delay.microseconds // 1000))

def setup(bot):
	bot.add_cog(General(bot))
