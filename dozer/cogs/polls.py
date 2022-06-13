"""Very simple polls cog. """
from logging import getLogger

import discord
from discord.ext.commands import has_permissions

from ._utils import *

DOZER_LOGGER = getLogger(__name__)


class Polls(Cog):
    """Polls cog for Dozer, code borrowed with love from https://github.com/Iarrova/Polling-Bot"""

    @command()
    @has_permissions(manage_messages=True)
    async def poll(self, ctx, *, poll_options):
        """Command to create a very simple poll."""
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            DOZER_LOGGER.debug("Could not delete poll invoke message. ")
        # Separate title and options
        splitted = poll_options.split('" ')
        title = splitted[0].replace('"', '')
        options = splitted[1:]
        newoptions = []
        for i in options:
            newoptions.append(i.replace('"', ''))
        options = newoptions
        # Check if there is more than 1 option
        if len(options) <= 1:
            embed = discord.Embed(
                description=':x: There must be at least 2 options to make a poll!',
                colour=discord.Colour.red(),
            )
            await ctx.send(embed=embed)
            return
        # Check if there are less than 20 options (because of Discord limits)
        if len(options) > 20:
            embed = discord.Embed(
                description=':x: There can\'t be more than 20 options',
                colour=discord.Colour.red(),
            )
            await ctx.send(embed=embed)
            return

        # Checks whether poll is a Yes/No Question or a Multiple Choice Question
        if len(options) == 2 and options[0].lower() == 'yes' and options[1].lower() == 'no':
            reactions = ['✅', '❌']
        else:
            # Regional Indicators
            reactions = ['🇦', '🇧', '🇨', '🇩', '🇪', '🇫', '🇬', '🇭', '🇮', '🇯', '🇰', '🇱', '🇲', '🇳', '🇴', '🇵',
                         '🇶', '🇷', '🇸', '🇹']

        # Create embed response
        description = []
        for x, option in enumerate(options):
            description += '{}  {}\n\n'.format(reactions[x], option)
        embed = discord.Embed(
            title=title,
            description=''.join(description),
            colour=discord.Colour.blue()
        )
        embed.set_footer(text="Invoked by " + ctx.author.display_name)
        message = await ctx.send(embed=embed)

        for reaction in reactions[:len(options)]:
            await message.add_reaction(reaction)

    poll.example_usage = (
        "`{prefix}poll \"Are polls cool?\" \"Yes\" \"No\"` - Makes a poll with 2 options. \n`{prefix}poll "
        "\"What should we name the robot?\" \"Bolt Bucket\" \"Susan\" \"Programming did it\"` - Makes a poll with "
        "the 3 listed options. ")


def setup(bot):
    """Adds the Polls cog to the bot."""
    bot.add_cog(Polls(bot))
