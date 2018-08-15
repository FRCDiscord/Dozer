"""Bot object for Dozer"""

import logging
import re
import sys
import traceback
import discord
from discord.ext import commands

from . import utils

DOZER_LOGGER = logging.Logger(name='dozer')
DOZER_LOGGER.level = logging.INFO
DOZER_HANDLER = logging.StreamHandler(stream=sys.stdout)
DOZER_HANDLER.level = logging.INFO
DOZER_LOGGER.addHandler(DOZER_HANDLER)
DOZER_HANDLER.setFormatter(fmt=logging.Formatter('[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s'))

if discord.version_info.major < 1:
    DOZER_LOGGER.error("Your installed discord.py version is too low "
                       "%d.%d.%d, please upgrade to at least 1.0.0a",
                       discord.version_info.major,
                       discord.version_info.minor,
                       discord.version_info.micro)
    sys.exit(1)


class InvalidContext(commands.CheckFailure):
    """
    Check failure raised by the global check for an invalid command context - executed by a bot, exceeding global rate-limit, etc.
    The message will be ignored.
    """


class DozerContext(commands.Context):
    """Cleans all messages before sending"""
    async def send(self, content=None, **kwargs):
        if content is not None:
            content = utils.clean(self, content, mass=True, member=False, role=False, channel=False)
        return await super().send(content, **kwargs)


class Dozer(commands.Bot):
    """Botty things that are critical to Dozer working"""
    _global_cooldown = commands.Cooldown(1, 1, commands.BucketType.user)  # One command per second per user

    def __init__(self, config):
        super().__init__(command_prefix=config['prefix'])
        self.config = config
        self._restarting = False
        self.check(self.global_checks)

    async def on_ready(self):
        """Things to run when the bot has initialized and signed in"""
        DOZER_LOGGER.info('Signed in as {}#{} ({})'.format(self.user.name, self.user.discriminator, self.user.id))
        if self.config['is_backup']:
            status = discord.Status.dnd
        else:
            status = discord.Status.online
        game = discord.Game(name='%shelp | %d guilds' % (self.config['prefix'], len(self.guilds)))
        try:
            await self.change_presence(activity=game, status=status)
        except TypeError:
            DOZER_LOGGER.warning("You are running an older version of the discord.py rewrite (with breaking changes)! "
                                 "To upgrade, run `pip install -r requirements.txt --upgrade`")

    async def get_context(self, message, *, cls=DozerContext):
        ctx = await super().get_context(message, cls=cls)
        return ctx

    async def on_command_error(self, context, exception):
        if isinstance(exception, commands.NoPrivateMessage):
            await context.send('{}, This command cannot be used in DMs.'.format(context.author.mention))
        elif isinstance(exception, commands.UserInputError):
            await context.send('{}, {}'.format(context.author.mention, self.format_error(context, exception)))
        elif isinstance(exception, commands.NotOwner):
            await context.send('{}, {}'.format(context.author.mention, exception.args[0]))
        elif isinstance(exception, commands.MissingPermissions):
            permission_names = [name.replace('guild', 'server').replace('_', ' ').title() for name in exception.missing_perms]
            await context.send('{}, you need {} permissions to run this command!'.format(
                context.author.mention, utils.pretty_concat(permission_names)))
        elif isinstance(exception, commands.BotMissingPermissions):
            permission_names = [name.replace('guild', 'server').replace('_', ' ').title() for name in exception.missing_perms]
            await context.send('{}, I need {} permissions to run this command!'.format(
                context.author.mention, utils.pretty_concat(permission_names)))
        elif isinstance(exception, commands.CommandOnCooldown):
            await context.send(
                '{}, That command is on cooldown! Try again in {:.2f}s!'.format(context.author.mention, exception.retry_after))
        elif isinstance(exception, (commands.CommandNotFound, InvalidContext)):
            pass  # Silent ignore
        else:
            await context.send('```\n%s\n```' % ''.join(traceback.format_exception_only(type(exception), exception)).strip())
            if isinstance(context.channel, discord.TextChannel):
                DOZER_LOGGER.error('Error in command <%d> (%d.name!r(%d.id) %d(%d.id) %d(%d.id) %d)',
                                   context.command, context.guild, context.guild, context.channel, context.channel,
                                   context.author, context.author, context.message.content)
            else:
                DOZER_LOGGER.error('Error in command <%d> (DM %d(%d.id) %d)', context.command, context.channel.recipient,
                                   context.channel.recipient, context.message.content)
            DOZER_LOGGER.error(''.join(traceback.format_exception(type(exception), exception, exception.__traceback__)))

    @staticmethod
    def format_error(ctx, err, *, word_re=re.compile('[A-Z][a-z]+')):
        """Turns an exception into a user-friendly (or -friendlier, at least) error message."""
        type_words = word_re.findall(type(err).__name__)
        type_msg = ' '.join(map(str.lower, type_words))

        if err.args:
            return '%s: %s' % (type_msg, utils.clean(ctx, err.args[0]))
        else:
            return type_msg

    def global_checks(self, ctx):
        """Checks that should be executed before passed to the command"""
        if ctx.author.bot:
            raise InvalidContext('Bots cannot run commands!')
        retry_after = self._global_cooldown.update_rate_limit()
        if retry_after:
            raise InvalidContext('Global rate-limit exceeded!')
        return True

    def run(self, *args, **kwargs):
        token = self.config['discord_token']
        del self.config['discord_token']  # Prevent token dumping
        super().run(token)

    async def shutdown(self, restart=False):
        """Shuts down the bot"""
        self._restarting = restart
        await self.logout()
        await self.close()
        self.loop.stop()
