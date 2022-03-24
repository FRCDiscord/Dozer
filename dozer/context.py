from discord.ext import commands

from dozer import utils


class DozerContext(commands.Context):
    """Cleans all messages before sending"""

    async def send(self, content=None, **kwargs):  # pylint: disable=arguments-differ
        """Make it so you cannot ping @.everyone when sending a message"""
        if content is not None:
            content = utils.clean(self, content, mass=True, member=False, role=False, channel=False)
        return await super().send(content, **kwargs)
