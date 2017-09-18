import asyncio, itertools
from discord.ext.commands import command, group

__all__ = ['command', 'group', 'Cog', 'Reactor', 'Paginator', 'paginate']

class Cog:
	def __init__(self, bot):
		self.bot = bot

class Reactor:
	"""
	A simple way to respond to Discord reactions.
	Usage:
		from ._utils import Reactor
		# in a command
		initial_reactions = [...] # Initial reactions (str or Emoji) to add
		reactor = Reactor(ctx, initial_reactions) # Timeout is optional, and defaults to 1 minute
		async for reaction in reactor:
			# reaction is the str/Emoji that was added.
			# reaction will not necessarily be in initial_reactions.
			if reaction == this_emoji:
				reactor.do(reactor.message.edit(content='This!')) # Any coroutine
			elif reaction == that_emoji:
				reactor.do(reactor.message.edit(content='That!'))
			elif reaction == stop_emoji:
				reactor.stop() # The next time around, the message will be deleted and the async-for will end
			# If no action is set (e.g. unknown emoji), nothing happens
	"""
	_stop_reaction = object()
	def __init__(self, ctx, initial_reactions, *, auto_remove=True, timeout=60):
		"""
		ctx: command context
		initial_reactions: iterable of emoji to react with on start
		auto_remove: if True, reactions are removed once processed
		timeout: time, in seconds, to wait before stopping automatically. Set to None to wait forever.
		"""
		self.dest = ctx.channel
		self.bot = ctx.bot
		self.member = ctx.author
		self._reactions = tuple(initial_reactions)
		self._remove_reactions = auto_remove
		self.timeout = timeout
		self._action = None
	
	async def __aiter__(self):
		self.message = await self.dest.send(embed=self.pages[self.page])
		for emoji in self._reactions:
			await self.message.add_reaction(emoji)
		while True:
			try:
				reaction, reacting_member = await self.bot.wait_for('reaction_add', check=self._check_reaction, timeout=self.timeout)
			except asyncio.TimeoutError:
				break
			
			yield reaction.emoji
			# Caller calls methods to set self._action; end of async for block, control resumes here
			if self._remove_reactions:
				await self.message.remove_reaction(reaction.emoji, reacting_member)
			if self._action is self._stop_reaction:
				break
			elif self._action is None:
				pass
			else:
				await self._action
		await self.message.delete()
	
	def do(self, action):
		self._action = action
	
	def stop(self):
		self._action = self._stop_reaction
	
	def _check_reaction(self, reaction, member):
		return reaction.message.id == self.message.id and member.id == self.member.id

class Paginator(Reactor):
	"""
	Extends functionality of Reactor for pagination.
	Left- and right- arrow reactions are used to move between pages.
	:stop: will stop the pagination.
	Other reactions are given to the caller like normal.
	Usage:
		from ._utils import Reactor
		# in a command
		initial_reactions = [...] # Initial reactions (str or Emoji) to add (in addition to normal pagination reactions)
		pages = [...] # Embeds to use for each page
		paginator = Paginator(ctx, initial_reactions, pages)
		async for reaction in paginator:
			# See Reactor for how to handle reactions
			# Paginator reactions will not be yielded here - only unknowns
	"""
	pagination_reactions = (
		'\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}', # :track_previous:
		'\N{BLACK LEFT-POINTING TRIANGLE}', # :arrow_backward:
		'\N{BLACK RIGHT-POINTING TRIANGLE}', # :arrow_forward:
		'\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}', # :track_next:
		'\N{BLACK SQUARE FOR STOP}' # :stop_button:
	)
	def __init__(self, ctx, initial_reactions, pages, *, start=0, auto_remove=True, timeout=60):
		super().__init__(ctx, itertools.chain(self.pagination_reactions + initial_reactions), auto_remove=auto_remove, timeout=timeout)
		self.pages = pages
		self.page = start
	
	async def __aiter__(self):
		self.reactor = super().__aiter__()
		async for reaction in self.reactor:
			try:
				ind = self.pagination_reactions.index(reaction)
			except ValueError: # Not in list - send to caller
				yield reaction
			else:
				if ind == 0:
					self.go_to_page(0)
				elif ind == 1:
					self.prev()
				elif ind == 2:
					self.next()
				elif ind == 3:
					self.go_to_page(-1)
				else: # Only valid option left is 4
					self.stop()
	
	def go_to_page(self, page):
		self.page = page % len(self.pages)
		if self.page < 0:
			self.page += len(self.pages)
		self.do(self.message.edit(embed=self.pages[self.page]))
	
	def next(self, amt=1):
		self.go_to_page(self.page + amt)
	
	def prev(self, amt=1):
		self.go_to_page(self.page - amt)

async def paginate(ctx, pages, *, start=0, auto_remove=True, timeout=60):
	"""
	Simple pagination based on Paginator. Pagination is handled normally and other reactions are ignored.
	"""
	paginator = Paginator(ctx, (), pages, start=start, auto_remove=auto_remove, timeout=timeout)
	async for reaction in paginator:
		pass # The normal pagination reactions are handled - just drop anything else
