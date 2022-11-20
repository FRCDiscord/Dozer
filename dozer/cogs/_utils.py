"""Utilities for Dozer."""
import asyncio
import inspect
from collections.abc import Mapping
from typing import Dict, Union, Optional, Any, Coroutine, List, Generator, Iterable, AsyncGenerator
from typing import TYPE_CHECKING

import discord
from discord import app_commands, Embed, Permissions
from discord.ext import commands
from discord.ext.commands import HybridCommand
from discord.ext.commands.core import MISSING
from loguru import logger

from dozer import db
from dozer.context import DozerContext

if TYPE_CHECKING:
    from dozer import Dozer

__all__ = ['bot_has_permissions', 'command', 'group', 'Cog', 'Reactor', 'Paginator', 'paginate', 'chunk', 'dev_check',
           'DynamicPrefixEntry', 'CommandMixin']




class CommandMixin:
    """Example usage processing"""

    # Keyword-arg dictionary passed to __init__ when copying/updating commands when Cog instances are created
    # inherited from discord.ext.command.Command
    __original_kwargs__: Dict[str, Any]
    _required_permissions = None

    def __init__(self, func: Union["Command", "Group"], **kwargs):
        super().__init__(func, **kwargs)
        self.example_usage: Optional[str] = kwargs.pop('example_usage', '')
        if hasattr(func, '__required_permissions__'):
            # This doesn't need to go into __original_kwargs__ because it'll be read from func each time
            self._required_permissions = func.__required_permissions__

    @property
    def required_permissions(self):
        """Required permissions handler"""
        if self._required_permissions is None:
            self._required_permissions = Permissions()
        return self._required_permissions

    @property
    def example_usage(self):
        """Example usage property"""
        return self._example_usage

    @example_usage.setter
    def example_usage(self, usage):
        """Sets example usage"""
        self._example_usage = self.__original_kwargs__['example_usage'] = inspect.cleandoc(usage)


class Command(CommandMixin, HybridCommand):
    """Represents a command"""


def command(**kwargs):
    """Represents bot commands"""
    kwargs.setdefault('cls', Command)
    return commands.command(**kwargs)


def group(**kwargs):
    """Links command groups"""
    kwargs.setdefault('cls', Group)
    return commands.group(**kwargs)


class Group(CommandMixin, commands.HybridGroup):
    """Class for command groups"""

    def command(
        self,
        name: Union[str, app_commands.locale_str] = MISSING,
        *args: Any,
        with_app_command: bool = True,
        **kwargs: Any,
    ):
        """Initiates a command"""

        def decorator(func):
            kwargs.setdefault('parent', self)
            result = command(name=name, with_app_command=with_app_command, **kwargs)(func)
            self.add_command(result)
            return result

        return decorator

    def group(
        self,
        name: Union[str, app_commands.locale_str] = MISSING,
        *args: Any,
        with_app_command: bool = True,
        **kwargs: Any,
    ):
        """Initiates a command group"""

        def decorator(func):
            kwargs.setdefault('parent', self)
            result = group(name=name, with_app_command=with_app_command, **kwargs)(func)
            self.add_command(result)
            return result

        return decorator


class Cog(commands.Cog):
    """Initiates cogs."""

    def __init__(self, bot: "Dozer"):
        super().__init__()
        self.bot: "Dozer" = bot

    def walk_commands(self) -> Generator[Union[Group, Command], None, None]:
        return super().walk_commands()


def dev_check():
    """Function decorator to check that the calling user is a developer"""

    async def predicate(ctx: DozerContext) -> bool:
        if ctx.author.id not in ctx.bot.config['developers']:
            raise commands.NotOwner('you are not a developer!')
        return True

    return commands.check(predicate)


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

    def __init__(self, ctx: DozerContext, initial_reactions, *, auto_remove: bool = True, timeout: int = 60):
        """
        ctx: command context
        initial_reactions: iterable of emoji to react with on start
        auto_remove: if True, reactions are removed once processed
        timeout: time, in seconds, to wait before stopping automatically. Set to None to wait forever.
        """
        self.dest = ctx.interaction.followup if ctx.interaction else ctx.channel
        self.bot = ctx.bot
        self.caller = ctx.author
        self.me = ctx.guild.get_member(self.bot.user.id)
        self._reactions = tuple(initial_reactions)
        self._remove_reactions = auto_remove and ctx.channel.permissions_for(
            self.me).manage_messages  # Check for required permissions
        self.timeout = timeout
        self._action: Optional[Coroutine] = None
        self.message = None
        self.pages: Dict[Union[int, str], Embed]
        self.page: Embed

    async def __aiter__(self):
        self.message = await self.dest.send(embed=self.pages[self.page])
        for emoji in self._reactions:
            await self.message.add_reaction(emoji)
        while True:
            try:
                reaction, reacting_member = await self.bot.wait_for('reaction_add', check=self._check_reaction,
                                                                    timeout=self.timeout)
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
        for emoji in reversed(self._reactions):
            try:
                await self.message.remove_reaction(emoji, self.me)
            except discord.errors.NotFound:
                logger.debug("Failed to remove reaction from paginator. Does the messages still exist?")

    def do(self, action):
        """If there's an action reaction, do the action."""
        self._action = action

    def stop(self):
        """Listener for stop reactions."""
        self._action = self._stop_reaction

    def _check_reaction(self, reaction: discord.Reaction, member: discord.Member):
        if self.message is not None:
            return reaction.message.id == self.message.id and member.id == self.caller.id
        return None


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
        '\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}',  # :track_previous:
        '\N{BLACK LEFT-POINTING TRIANGLE}',  # :arrow_backward:
        '\N{BLACK RIGHT-POINTING TRIANGLE}',  # :arrow_forward:
        '\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}',  # :track_next:
        '\N{BLACK SQUARE FOR STOP}'  # :stop_button:
    )

    def __init__(self, ctx: DozerContext, initial_reactions: Iterable[discord.Reaction], pages: List[Union[Embed, Dict[str, Embed]]], *,
                 start: Union[int, str] = 0, auto_remove: bool = True, timeout: int = 60):
        all_reactions = list(initial_reactions)
        ind: int = all_reactions.index(Ellipsis)
        all_reactions[ind:ind + 1] = self.pagination_reactions
        super().__init__(ctx, all_reactions, auto_remove=auto_remove, timeout=timeout)
        if pages and isinstance(pages[-1], Mapping):
            named_pages: Dict[str, Embed] = pages.pop()
            # The following code assembles the list of Embeds into a dict with the indexes as keys, and with the named pages.
            self.pages = {**{k: v for v, k in enumerate(pages)}, **named_pages}
        else:
            self.pages = pages
        self.len_pages: int = len(pages)
        self.page: Union[int, str] = start
        self.message: Optional[discord.Message] = None
        self.reactor: Optional[AsyncGenerator] = None

    async def __aiter__(self):
        self.reactor = super().__aiter__()
        async for reaction in self.reactor:
            try:
                ind = self.pagination_reactions.index(reaction)
            except ValueError:  # Not in list - send to caller
                yield reaction
            else:
                if ind == 0:
                    self.go_to_page(0)
                elif ind == 1:
                    self.prev()  # pylint: disable=not-callable
                elif ind == 2:
                    self.next()  # pylint: disable=not-callable
                elif ind == 3:
                    self.go_to_page(-1)
                else:  # Only valid option left is 4
                    self.stop()

    def go_to_page(self, page: Union[int, str]):
        """Goes to a specific help page"""
        if isinstance(page, int):
            page = page % self.len_pages
            if page < 0:
                page += self.len_pages
        self.page = page
        if self.message is not None:
            self.do(self.message.edit(embed=self.pages[self.page]))

    def next(self, amt: int = 1):
        """Goes to the next help page"""
        if isinstance(self.page, int):
            self.go_to_page(self.page + amt)
        else:
            self.go_to_page(amt - 1)

    def prev(self, amt: int = 1):
        """Goes to the previous help page"""
        if isinstance(self.page, int):
            self.go_to_page(self.page - amt)
        else:
            self.go_to_page(-amt)


async def paginate(ctx: DozerContext, pages, *, start: int = 0, auto_remove: bool = True, timeout: int = 60):
    """
    Simple pagination based on Paginator. Pagination is handled normally and other reactions are ignored.
    """
    paginator = Paginator(ctx, [...], pages, start=start, auto_remove=auto_remove, timeout=timeout)
    async for reaction in paginator:
        pass  # The normal pagination reactions are handled - just drop anything else


def chunk(iterable, size: int) -> Iterable[Iterable]:
    """
    Break an iterable into chunks of a fixed size. Returns an iterable of iterables.
    Almost-inverse of itertools.chain.from_iterable - passing the output of this into that function will reconstruct the original iterable.
    If the last chunk is not the full length, it will be returned but not padded.
    """
    contents: List = list(iterable)
    for i in range(0, len(contents), size):
        yield contents[i:i + size]


def bot_has_permissions(**required):
    """Decorator to check if bot has certain permissions when added to a command"""

    def predicate(ctx: DozerContext):
        """Function to tell the bot if it has the right permissions"""
        given: Permissions = ctx.channel.permissions_for((ctx.guild or ctx.channel).me)
        missing: List[str] = [name for name, value in required.items() if getattr(given, name) != value]

        if missing:
            raise commands.BotMissingPermissions(missing)
        else:
            return True

    def decorator(func):
        """Defines the bot_has_permissions decorator"""
        if isinstance(func, Command):
            func.checks.append(predicate)
            func.required_permissions.update(**required)
        else:
            if hasattr(func, '__commands_checks__'):
                func.__commands_checks__.append(predicate)
            else:
                func.__commands_checks__ = [predicate]
            func.__required_permissions__ = Permissions()
            func.__required_permissions__.update(**required)
        return func

    return decorator


class PrefixHandler:
    """Handles dynamic prefixes"""

    def __init__(self, default_prefix: str):
        self.default_prefix = default_prefix
        self.prefix_cache: Dict[int, DynamicPrefixEntry] = {}

    def handler(self, bot, message: discord.Message):
        """Process the dynamic prefix for each message"""
        dynamic = self.prefix_cache.get(message.guild.id) if message.guild else None
        # <@!> is a nickname mention which discord.py doesn't make by default
        return [f"<@!{bot.user.id}> ", f"<@!{bot.user.id}>", bot.user.mention, bot.user.mention + " ",
                dynamic.prefix if dynamic else self.default_prefix]

    async def refresh(self):
        """Refreshes the prefix cache"""
        prefixes = await DynamicPrefixEntry.get_by()  # no filters, get all
        for prefix in prefixes:
            self.prefix_cache[prefix.guild_id] = prefix
        logger.info(f"{len(prefixes)} prefixes loaded from database")


class DynamicPrefixEntry(db.DatabaseTable):
    """Holds the custom prefixes for guilds"""
    __tablename__ = 'dynamic_prefixes'
    __uniques__ = 'guild_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
                CREATE TABLE {cls.__tablename__} (
                guild_id bigint NOT NULL,
                prefix text NOT NULL,
                PRIMARY KEY (guild_id)
                )""")

    def __init__(self, guild_id: int, prefix: str):
        super().__init__()
        self.guild_id = guild_id
        self.prefix = prefix

    @classmethod
    async def get_by(cls, **kwargs) -> List["DynamicPrefixEntry"]:
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = DynamicPrefixEntry(guild_id=result.get("guild_id"), prefix=result.get("prefix"))
            result_list.append(obj)
        return result_list
