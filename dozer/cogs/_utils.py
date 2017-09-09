from discord.ext.commands import command, group

__all__ = ['command', 'group', 'Cog']

class Cog:
	def __init__(self, bot):
		self.bot = bot
