import discord
from discord.ext import commands

class Dozer(commands.Bot):
	def __init__(self, config):
		super().__init__(command_prefix=config['prefix'])
		self.config = config
	
	async def on_ready(self):
		print('Signed in as {0!s} ({0.id})'.format(self.user))
		await self.change_presence(game=discord.Game(name='%shelp | %d guilds' % (self.config['prefix'], len(self.guilds))))
	
	def run(self):
		token = self.config['discord_token']
		del self.config['discord_token'] # Prevent token dumping
		super().run(token)
	
	async def shutdown(self):
		await self.logout()
		await self.close()
		self.loop.stop()
