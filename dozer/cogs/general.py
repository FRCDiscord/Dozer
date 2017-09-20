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
		await self._show_help(ctx, None, '', '', 'all commands', ctx.bot.commands)
	
	async def _help_command(self, ctx, command):
		"""Gets the help message for one command."""
		await self._show_help(ctx, None, 'Command: {prefix}{command.signature}', command.help, '{command.qualified_name!r} command', command.commands if isinstance(command, Group) else set(), command=command)
	
	async def _help_cog(self, ctx, cog):
		"""Gets the help message for one cog."""
		await self._show_help(ctx, None, 'Category: {cog_name}', cog.__doc__ or '', '{cog_name!r} category', (command for command in ctx.bot.commands if command.instance is cog), cog_name=type(cog).__name__)
	
	async def _show_help(self, ctx, start_page, title, description, footer, commands, **format_args):
		"""Creates and sends a template help message, with arguments filled in."""
		format_args['prefix'] = ctx.prefix
		footer = 'Dozer Help | {} | Page {}'.format(footer, '{page_num} of {len_pages}') # Page info is inserted as a parameter so page_num and len_pages aren't evaluated now
		if commands:
			command_chunks = list(chunk(sorted(commands, key=lambda cmd: cmd.name), 4))
			format_args['len_pages'] = len(command_chunks)
			pages = []
			for page_num, page_commands in enumerate(command_chunks):
				format_args['page_num'] = page_num + 1
				page = discord.Embed(title=title.format(**format_args), description=description.format(**format_args), color=discord.Color.blue())
				for command in page_commands:
					page.add_field(name=ctx.prefix + command.signature, value=command.help.splitlines()[0], inline=False)
				page.set_footer(text=footer.format(**format_args))
				pages.append(page)
			
			if start_page is not None:
				pages.append({'info': start_page})
			
			if len(pages) == 1:
				await ctx.send(embed=pages[0])
			elif start_page is not None:
				info_emoji = '\N{INFORMATION SOURCE}'
				p = Paginator(ctx, (info_emoji, ...), pages, start='info', auto_remove=ctx.channel.permissions_for(ctx.me))
				async for reaction in p:
					if reaction == info_emoji:
						p.go_to_page('info')
			else:
				await paginate(ctx, pages, auto_remove=ctx.channel.permissions_for(ctx.me))
		else: # No commands - command with no subcommands, empty cog, or command-less bot
			format_args['len_pages'] = 1
			format_args['page_num'] = 1
			embed = discord.Embed(title=title.format(**format_args), description=description.format(**format_args), color=discord.Color.blue())
			embed.set_footer(text=footer.format(**format_args))
			await ctx.send(embed=embed)

def setup(bot):
	bot.remove_command('help')
	bot.add_cog(General(bot))
