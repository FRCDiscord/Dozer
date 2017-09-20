import discord
from discord.ext.commands import BadArgument, Group
from ._utils import *

class General(Cog):
	"""General commands common to all Discord bots."""
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
	
	@command(name='help')
	async def base_help(self, ctx, *target):
		"""Show this message."""
		if not target: # No commands - general help
			await self._help_all(ctx)
		elif len(target) == 1: # Cog or command
			target_name = target[0]
			if target_name in ctx.bot.cogs:
				await self._help_cog(ctx, ctx.bot.cogs[target_name])
			else:
				command = ctx.bot.get_command(target_name)
				if command is None:
					raise BadArgument('that command/cog does not exist!')
				else:
					await self._help_command(ctx, command)
		else: # Command with subcommand
			command = ctx.bot.get_command(' '.join(target))
			if command is None:
				raise BadArgument('that command does not exist!')
			else:
				await self._help_command(ctx, command)
	
	async def _help_all(self, ctx):
		"""Gets the help message for all commands."""
		pages = []
		command_chunks = list(chunk(sorted(ctx.bot.commands, key=lambda cmd: cmd.qualified_name), 4))
		for page_num, page_commands in enumerate(command_chunks):
			page = discord.Embed(color=discord.Color.blue())
			for command in page_commands:
				page.add_field(name=ctx.prefix + command.signature, value=command.help.splitlines()[0], inline=False)
			page.set_footer(text='Dozer Help | Page {} of {}'.format(page_num + 1, len(command_chunks)))
			pages.append(page)
		await paginate(ctx, pages, auto_remove=ctx.channel.permissions_for(ctx.me))
	
	async def _help_command(self, ctx, command):
		"""Gets the help message for one command."""
		if not isinstance(command, Group):
			e = discord.Embed(title=ctx.prefix + command.signature, description=command.help, color=discord.Color.blue())
			e.set_footer(text='Dozer Help | {}'.format(command.qualified_name))
			await ctx.send(embed=e)
			return
		
		pages = []
		command_chunks = list(chunk(sorted(command.commands, key=lambda cmd: cmd.qualified_name), 4))
		for page_num, page_commands in enumerate(command_chunks):
			page = discord.Embed(title=ctx.prefix + command.signature, description=command.help, color=discord.Color.blue())
			for subcommand in page_commands:
				page.add_field(name=ctx.prefix + subcommand.signature, value=subcommand.help.splitlines()[0], inline=False)
			page.set_footer(text='Dozer Help | {} | Page {} of {}'.format(command.qualified_name, page_num + 1, len(command_chunks)))
			pages.append(page)
		await paginate(ctx, pages, auto_remove=ctx.channel.permissions_for(ctx.me))
	
	async def _help_cog(self, ctx, cog):
		"""Gets the help message for one cog."""
		cog_name = type(cog).__name__
		commands = sorted((command for command in ctx.bot.commands if command.instance is cog), key=lambda cmd: cmd.qualified_name)
		command_chunks = list(chunk(commands, 4))
		pages = []
		for page_num, page_commands in enumerate(command_chunks):
			page = discord.Embed(title=cog_name, description=cog.__doc__, color=discord.Color.blue())
			for command in page_commands:
				page.add_field(name=ctx.prefix + command.signature, value=command.help.splitlines()[0], inline=False)
			page.set_footer(text='Dozer Help | {} cog | Page {} of {}'.format(cog_name, page_num + 1, len(command_chunks)))
			pages.append(page)
		await paginate(ctx, pages, auto_remove=ctx.channel.permissions_for(ctx.me))

def setup(bot):
	bot.remove_command('help')
	bot.add_cog(General(bot))
