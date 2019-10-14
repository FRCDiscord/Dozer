"""Maintenance commands for bot developers"""

import os
import sys

from discord.ext.commands import NotOwner

from dozer.bot import DOZER_LOGGER
from ._utils import *


class Maintenance(Cog):
    """
    Commands for performing maintenance on the bot.
    These commands are restricted to bot developers.
    """

    def cog_check(self, ctx):  # All of this cog is only available to devs
        if ctx.author.id not in ctx.bot.config['developers']:
            raise NotOwner('you are not a developer!')
        return True

    @command()
    async def shutdown(self, ctx):
        """Force-stops the bot."""
        await ctx.send('Shutting down')
        DOZER_LOGGER.info('Shutting down at request of {}#{} (in {}, #{})'.format(ctx.author.name,
                                                                                  ctx.author.discriminator,
                                                                                  ctx.guild.name,
                                                                                  ctx.channel.name))
        await self.bot.shutdown()

    shutdown.example_usage = """
    `{prefix}shutdown` - stop the bot
    """

    @command()
    async def restart(self, ctx):
        """Restarts the bot."""
        await ctx.send('Restarting')
        await self.bot.shutdown(restart=True)

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
        res = os.popen("git pull").read()
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
