"""Provides modmail functions for Dozer."""

import discord
from discord import ui
from discord.ext import commands
from discord.ext.commands import has_permissions

from dozer.context import DozerContext
from ._utils import *
from .. import db


class Buttons(discord.ui.View):
    """Buttons? Buttons."""
    def __init__(self, *, timeout=None):  # timeout should be None for persistence
        super().__init__(timeout=timeout)

    @discord.ui.button(label="Start Modmail", style=discord.ButtonStyle.blurple, custom_id="modmail_button")
    async def start_modmail_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Callback for button to show modal"""
        # print("Button pressed") # When button is pressed just output that it was pressed
        await interaction.response.send_modal(StartModmailModal(title="New Modmail"))


class StartModmailModal(ui.Modal):
    """Modal for opening a modmail ticket"""

    subject = ui.TextInput(label='Subject')
    message = ui.TextInput(label='Message', style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        """Handles when a modal is submitted"""
        target_record = await ModmailConfig.get_by(guild_id=interaction.guild_id)
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
    async def configure_modmail(self, ctx: DozerContext, target_channel):
        """Modmail configuration command. target_channel may be in another guild."""
        config = ModmailConfig(ctx.guild.id, int(target_channel))
        await config.update_or_add()
        await ctx.reply("Configuration saved!")

    @command()
    @has_permissions(administrator=True)
    async def create_modmail_button(self, ctx):
        """Creates modmail button"""
        view = Buttons()
        await ctx.send("Click the button to start a new modmail thread!", view=view)

    @command()
    async def start_modmail(self, ctx: DozerContext):
        """Starts a modmail interaction"""
        target_record = await ModmailConfig.get_by(guild_id=ctx.guild.id)
        if len(target_record) == 0:
            await ctx.reply("Modmail is not configured for this server!")
            return
        await ctx.interaction.response.send_modal(StartModmailModal(title="New Modmail"))


class ModmailConfig(db.DatabaseTable):
    """Holds configurations for modmail"""
    __tablename__ = "modmail_config"
    __uniques__ = "guild_id"

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint NOT NULL UNIQUE,
            target_channel bigint NOT NULL
            )""")

    def __init__(self, guild_id: int, target_channel: int):
        super().__init__()
        self.guild_id = guild_id
        self.target_channel = target_channel

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = ModmailConfig(guild_id=result.get("guild_id"), target_channel=result.get("target_channel"))
            result_list.append(obj)
        return result_list


async def setup(bot):
    """Adds the actionlog cog to the bot."""
    await bot.add_cog(Modmail(bot))
