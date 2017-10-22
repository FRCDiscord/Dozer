import copy, discord, importlib, re
from discord.ext.commands import NotOwner
from ._utils import *

class Development(Cog):
	"""
	Commands useful for developing the bot.
	These commands are restricted to bot developers.
	"""
	eval_globals = {}
	for module in ('asyncio', 'collections', 'discord', 'inspect', 'itertools'):
		eval_globals[module] = __import__(module)
	eval_globals['__builtins__'] = __import__('builtins')
	
	def __local_check(self, ctx): # All of this cog is only available to devs
		if ctx.author.id not in ctx.bot.config['developers']:
			raise NotOwner('you are not a developer!')
		return True

	@command()
	async def reload(self, ctx, cog):
		"""Reloads a cog."""
		extension = 'dozer.cogs.' + cog
		msg = await ctx.send('Reloading extension %s' % extension)
		self.bot.unload_extension(extension)
		self.bot.load_extension(extension)
		await msg.edit(content='Reloaded extension %s' % extension)
	
	reload.example_usage = """
	`{prefix}reload development` - Reloads the development cog
	"""
	
	@command(name='eval')
	async def evaluate(self, ctx, *, code):
		"""
		Evaluates Python.
		Await is valid and `{ctx}` is the command context.
		"""
		if code.startswith('```'): code = code.strip('```').partition('\n')[2].strip() # Remove multiline code blocks
		else: code = code.strip('`').strip() # Remove single-line code blocks, if necessary
		
		e = discord.Embed(type='rich')
		e.add_field(name='Code', value='```py\n%s\n```' % code, inline=False)
		try:
			locals_ = locals()
			load_function(code, self.eval_globals, locals_)
			ret = await locals_['evaluated_function'](ctx)
			
			e.title = 'Python Evaluation - Success'
			e.color = 0x00FF00
			e.add_field(name='Output', value='```\n%s (%s)\n```' % (repr(ret), type(ret).__name__), inline=False)
		except Exception as err:
			e.title = 'Python Evaluation - Error'
			e.color = 0xFF0000
			e.add_field(name='Error', value='```\n%s\n```' % repr(err))
		await ctx.send(embed=e)
	
	evaluate.example_usage = """
	`{prefix}eval 0.1 + 0.2` - Calculates 0.1 + 0.2 which returns 0.3
	`{prefix}eval await ctx.send('Hello world!')` - Sends "Hello World!" to this channel
	"""
	
	@command(name='su', pass_context=True)
	async def pseudo(self, ctx, user : discord.Member, *, command):
		"""Execute a command as another user."""
		msg = copy.copy(ctx.message)
		msg.author = user
		msg.content = command
		context = await self.bot.get_context(msg)
		return await self.bot.invoke(context)
	
	pseudo.example_usage = """
	`{prefix}su cooldude#1234 {prefix}ping` - Simulate Cooldude sending `{prefix}ping`
	"""

def load_function(code, globals_, locals_):
	function_header = 'async def evaluated_function(ctx):'
	
	lines = code.splitlines()
	if len(lines) > 1:
		indent = 4
		for line in lines:
			line_indent = re.search(r'\S', line).start() # First non-WS character is length of indent
			if line_indent:
				indent = line_indent
				break
		line_sep = '\n' + ' ' * indent
		exec(function_header + line_sep + line_sep.join(lines), globals_, locals_)
	else:
		try:
			exec(function_header + '\n\treturn ' + lines[0], globals_, locals_)
		except SyntaxError as err: # Either adding the 'return' caused an error, or it's user error
			if err.text[err.offset-1] == '=' or err.text[err.offset-3:err.offset] == 'del' or err.text[err.offset-6:err.offset] == 'return': # return-caused error
				exec(function_header + '\n\t' + lines[0], globals_, locals_)
			else: # user error
				raise err

def setup(bot):
	bot.add_cog(Development(bot))
