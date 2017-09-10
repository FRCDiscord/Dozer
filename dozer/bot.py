import discord, re, traceback
from discord.ext import commands
from . import utils

class Dozer(commands.Bot):
	def __init__(self, config):
		super().__init__(command_prefix=config['prefix'])
		self.config = config
	
	async def on_ready(self):
		print('Signed in as {0!s} ({0.id})'.format(self.user))
		await self.change_presence(game=discord.Game(name='%shelp | %d guilds' % (self.config['prefix'], len(self.guilds))))
	
	async def on_command_error(self, ctx, err):
		if isinstance(err, commands.NoPrivateMessage):
			await ctx.send('This command cannot be used in DMs.')
		elif isinstance(err, commands.UserInputError):
			await ctx.send(self.format_error(ctx, err))
		else:
			await ctx.send('```\n%s\n```' % ''.join(traceback.format_exception_only(type(err), err)).strip())
			if isinstance(ctx.channel, discord.TextChannel):
				print('Error in command <{0}> ({1.name!r}({1.id}) {2}({2.id}) {3}({3.id}) {4!r})'.format(ctx.command, ctx.guild, ctx.channel, ctx.author, ctx.message.content))
			else:
				print('Error in command <{0}> (DM {1}({1.id}) {2!r})'.format(ctx.command, ctx.channel.recipient, ctx.message.content))
			traceback.print_exception(type(err), err, err.__traceback__)
	
	@staticmethod
	def format_error(ctx, err, *, word_re=re.compile('[A-Z][a-z]+')):
		type_words = word_re.findall(type(err).__name__)
		if len(type_words) == 1:
			type_msg = type_words[0]
		else:
			type_msg = type_words[0] + ' ' + ' '.join(map(str.lower, type_words[1:]))
		
		if err.args:
			return '%s: %s' % (type_msg, utils.clean(ctx, err.args[0]))
		else:
			return type_msg

	def run(self):
		token = self.config['discord_token']
		del self.config['discord_token'] # Prevent token dumping
		super().run(token)
	
	async def shutdown(self):
		await self.logout()
		await self.close()
		self.loop.stop()
