"""Class that holds dozercontext. """
from typing import TYPE_CHECKING

import discord
from discord.ext import commands


from dozer import utils

if TYPE_CHECKING:
    from dozer import Dozer


class DozerContext(commands.Context):
    """Cleans all messages before sending"""
    bot: "Dozer"
    # @property
    # def bot(self) -> "Dozer":
    #     """Returns the bot, with the correct type. """
    #     return super().bot

    async def send(self, content: str = None, **kwargs) -> discord.Message:  # pylint: disable=arguments-differ
        """Make it so you cannot ping @.everyone when sending a message"""
        if content is not None:
            content = utils.clean(self, content, mass=True, member=False, role=False, channel=False)
        return await super().send(content, **kwargs)
