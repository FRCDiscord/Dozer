import discord, re, traceback
from discord.ext import commands
from . import utils

class InvalidContext(commands.CheckFailure):
	"""
	Check failure raised by the global check for an invalid command context - executed by a bot, exceeding global rate-limit, etc.
	The message will be ignored.
	"""

class Dozer(commands.Bot):
	_global_cooldown = commands.Cooldown(1, 1, commands.BucketType.user) # One command per second per user
	def __init__(self, config):
		super().__init__(command_prefix=config['prefix'])
		self.config = config
		self.check(self.global_checks)
	
	async def on_ready(self):
		print('Signed in as {0!s} ({0.id})'.format(self.user))
		await self.change_presence(game=discord.Game(name='%shelp | %d guilds' % (self.config['prefix'], len(self.guilds))))
	
	async def on_command_error(self, ctx, err):
		if isinstance(err, commands.NoPrivateMessage):
			await ctx.send('{}, This command cannot be used in DMs.'.format(ctx.author.mention))
		elif isinstance(err, commands.UserInputError):
			await ctx.send('{}, {}'.format(ctx.author.mention, self.format_error(ctx, err)))
		elif isinstance(err, commands.NotOwner):
			await ctx.send('{}, {}'.format(ctx.author.mention, err.args[0]))
		elif isinstance(err, commands.MissingPermissions):
			permission_names = [name.replace('guild', 'server').replace('_', ' ').title() for name in err.missing_perms]
			await ctx.send('{}, you need {} permissions to run this command!'.format(ctx.author.mention, utils.pretty_concat(permission_names)))
		elif isinstance(err, commands.BotMissingPermissions):
			permission_names = [name.replace('guild', 'server').replace('_', ' ').title() for name in err.missing_perms]
			await ctx.send('{}, I need {} permissions to run this command!'.format(ctx.author.mention, utils.pretty_concat(permission_names)))
		elif isinstance(err, (commands.CommandNotFound, InvalidContext)):
			pass # Silent ignore
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
		type_msg = ' '.join(map(str.lower, type_words))
		
		if err.args:
			return '%s: %s' % (type_msg, utils.clean(ctx, err.args[0]))
		else:
			return type_msg
	
	def global_checks(self, ctx):
		if ctx.author.bot:
			raise InvalidContext('Bots cannot run commands!')
		if self._global_cooldown.is_rate_limited():
			raise InvalidContext('Global rate-limit exceeded!')
		return True
	
	def run(self):
		token = self.config['discord_token']
		del self.config['discord_token'] # Prevent token dumping
		super().run(token)
	
	async def shutdown(self):
		await self.logout()
		await self.close()
		self.loop.stop()
