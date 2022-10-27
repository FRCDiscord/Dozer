"""Provides modmail functions for Dozer."""

import discord
from discord import ui
from discord.ext.commands import has_permissions

from dozer.context import DozerContext
from discord.ext import commands
from ._utils import *
from .. import db


class StartModmailModal(ui.Modal):
    """Modal for opening a modmail ticket"""

    subject = ui.TextInput(label='Subject')
    message = ui.TextInput(label='Message', style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        """Handles when a modal is submitted"""
        target_record = await ModmailConfig.get_by(source_channel=interaction.channel_id)
        if len(target_record) == 0:
            print("No modmail config found!")
        elif len(target_record) == 1:
            print("do the thing")
        else:
            print("There has been a critical error. Please contact the Dozer devs.")


class Modmail(Cog):
    """A cog for Dozer's modmail functions"""
    def __init__(self, bot: commands.Bot):
        super().__init__(bot)

    @command()
    @has_permissions(administrator=True)
    async def configure_modmail(self, ctx: DozerContext, source_channel: discord.TextChannel, target_channel):
        """Modmail configuration command. target_channel may be in another guild."""
        ui.Modal()
        config = ModmailConfig(source_channel.id, int(target_channel))
        await config.update_or_add()
        await ctx.reply("Configuration saved!")


class ModmailConfig(db.DatabaseTable):
    """Holds configurations for modmail"""
    __tablename__ = "modmail_config"
    __uniques__ = "source_channel"

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            source_channel bigint NOT NULL UNIQUE,
            target_channel bigint NOT NULL
            )""")

    def __init__(self, source_channel: int, target_channel: int):
        super().__init__()
        self.source_channel = source_channel
        self.target_channel = target_channel

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = ModmailConfig(source_channel=result.get("source_channel"), target_channel=result.get("target_channel"))
            result_list.append(obj)
        return result_list


async def setup(bot):
    """Adds the actionlog cog to the bot."""
    await bot.add_cog(Modmail(bot))
