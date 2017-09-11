import os, sys
from ._utils import *
from discord.ext.commands import NotOwner

class Maintenance(Cog):
	def __local_check(self, ctx): # All of this cog is only available to devs
		if ctx.author.id not in ctx.bot.config['developers']:
			raise NotOwner('you are not a developer!')
		return True
	
	@command()
	async def shutdown(self, ctx):
		"""Force-stops the bot."""
		await ctx.send('Shutting down')
		print('Shutting down at request of {0.author} (in {0.guild}, #{0.channel})'.format(ctx))
		await self.bot.shutdown()
	
	@command()
	async def restart(self, ctx):
		"""Restarts the bot."""
		await ctx.send('Restarting')
		await self.bot.shutdown()
		script = sys.argv[0]
		if script.startswith(os.getcwd()):
			script = script[len(os.getcwd()):].lstrip(os.sep)
		
		if script.endswith('__main__.py'):
			args = [sys.executable, '-m', script[:-len('__main__.py')].rstrip(os.sep).replace(os.sep, '.')]
		else:
			args = [sys.executable, script]
		os.execv(sys.executable, args + sys.argv[1:])
	
	@command()
	async def update(self, ctx):
		"""Pulls code from GitHub and restarts."""
		res = os.popen("git pull origin master").read()
		if res.startswith('Already up-to-date.'):
			await ctx.send('```\n' + res + '```')
		else:
			await ctx.send('```\n' + res + '```')
			ctx.bot.get_command('restart').callback

def setup(bot):
	bot.add_cog(Maintenance(bot))
