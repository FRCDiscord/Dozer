"""Maintenance commands for bot developers"""

import os
import sys

from discord.ext.commands import NotOwner

from dozer.bot import DOZER_LOGGER
from ._utils import *

logger = DOZER_LOGGER


class Maintenance(Cog):
    """
    Commands for performing maintenance on the bot.
    These commands are restricted to bot developers.
    """

    def __local_check(self, ctx):  # All of this cog is only available to devs
        if ctx.author.id not in ctx.bot.config['developers']:
            raise NotOwner('you are not a developer!')
        return True

    @command()
    async def shutdown(self, ctx):
        """Force-stops the bot."""
        await ctx.send('Shutting down')
        logger.info('Shutting down at request of {0.author} (in {0.guild}, #{0.channel})'.format(ctx))
        await self.bot.shutdown()

    shutdown.example_usage = """
    `{prefix}shutdown` - stop the bot
    """

    @command()
    async def restart(self, ctx):
        """Restarts the bot."""
        await ctx.send('Restarting')
        await self.bot.shutdown()
        script = sys.argv[0]
        if script.startswith(os.getcwd()):
            script = script[len(os.getcwd()):].lstrip(os.sep)

        if script.endswith('__main__.py'):
            args = [sys.executable, '-m', script[:-len('__main__.py')].rstrip(os.sep).replace(os.sep, '.')]
        else:
            args = [sys.executable, script]
        os.execv(sys.executable, args + sys.argv[1:])

    restart.example_usage = """
    `{prefix}restart` - restart the bot
    """

    @command()
    async def update(self, ctx):
        """
        Pulls code from GitHub and restarts.
        This pulls from whatever repository `origin` is linked to.
        If there are changes to download, and the download is successful, the bot restarts to apply changes.
        """
        res = os.popen("git pull origin master").read()
        if res.startswith('Already up-to-date.'):
            await ctx.send('```\n' + res + '```')
        else:
            await ctx.send('```\n' + res + '```')
            await ctx.bot.get_command('restart').callback(self, ctx)

    update.example_usage = """
    `{prefix}update` - update to the latest commit and restart
    """


def setup(bot):
    """Adds the maintenance cog to the bot process."""
    bot.add_cog(Maintenance(bot))
