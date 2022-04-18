"""Very simple polls cog. """
import asyncio
import datetime
import logging
import re
import time
import typing
from logging import getLogger
from typing import Union

import discord
from discord.ext import tasks
from discord.ext.commands import BadArgument, has_permissions, RoleConverter, guild_only

from ._utils import *
from .general import blurple
from .. import db


class Polls(Cog):
    """Polls cog for Dozer, code borrowed with love from https://github.com/Iarrova/Polling-Bot"""
    def __init__(self, bot):
        super().__init__(bot)

    @command()
    async def poll(self, ctx, *, text):
        """Command to create a very simple poll."""
        # Delete called command
        await ctx.message.delete()

        # Separate title and options
        splitted = text.split('" ')
        title = splitted[0].replace('"', '')
        options = splitted[1:]
        for i in range(len(options)):
            options[i] = options[i].replace('"', '')

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

        # Checks wether poll is a Yes/No Question or a Multiple Choice Question
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
        message = await ctx.send(embed=embed)

        for reaction in reactions[:len(options)]:
            await message.add_reaction(reaction)


def setup(bot):
    """Adds the moderation cog to the bot."""
    bot.add_cog(Polls(bot))
