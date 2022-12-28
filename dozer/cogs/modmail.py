"""Provides modmail functions for Dozer."""
import datetime
import io

import discord
from discord import ui
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
        target_record = await ModmailConfig.get_by(guild_id=interaction.guild_id)
        if len(target_record) == 0:
            await interaction.response.send_message("Sorry, this server has not configured modmail correctly yet!")
        else:
            await interaction.response.send_modal(StartModmailModal(title="New Modmail"))


class StartModmailModal(ui.Modal):
    """Modal for opening a modmail ticket"""

    subject = ui.TextInput(label='Subject', custom_id="subject")
    message = ui.TextInput(label='Message', style=discord.TextStyle.paragraph, custom_id="message")

    async def on_submit(self, interaction: discord.Interaction):  # pylint: disable=arguments-differ
        """Handles when a modal is submitted"""
        subject = interaction.data['components'][0]['components'][0]['value']
        message = interaction.data['components'][1]['components'][0]['value']

        new_ticket_embed = discord.Embed(
            title="New Ticket",
            description="Send a message with /reply to reply. Messages are ignored, and can be used "
                        "for staff discussion.",
            timestamp=datetime.datetime.utcnow(),
        )
        new_ticket_embed.set_footer(
            text=f"{interaction.user.name}#{interaction.user.discriminator} | {interaction.user.id}",
            icon_url=interaction.user.avatar.url if interaction.user.avatar is not None else None,
        )
        target_record = await ModmailConfig.get_by(guild_id=interaction.guild_id)
        mod_channel = interaction.client.get_channel(target_record[0].target_channel)
        user_string = f"{interaction.user.name}#{interaction.user.discriminator} ({interaction.user.id})"
        mod_message = await mod_channel.send(user_string)
        mod_thread = await mod_channel.create_thread(name=subject, message=mod_message)
        await mod_thread.send(embed=new_ticket_embed)

        await interaction.response.send_message("Creating private modmail thread!", ephemeral=True)
        user_thread = await interaction.channel.create_thread(name=subject)
        await user_thread.add_user(interaction.user)
        await user_thread.join()
        thread_record = ModmailThreads(user_thread=user_thread.id, mod_thread=mod_thread.id)
        await thread_record.update_or_add()

        # PyCharm gets mad because modmail_cog is not initialized as the correct type globally, but is initialized
        # during setup. This warning can safely be ignored.
        await Modmail.send_modmail_embeds(modmail_cog, source_channel=user_thread.id, message_content=message)


class Modmail(Cog):
    """A cog for Dozer's modmail functions"""

    async def send_modmail_embeds(self, source_channel, message_content, received_files=None):
        """Helper function to send modmail message embeds."""
        if received_files is None:
            received_files = []
        lookup = await ModmailThreads.get_by(user_thread=source_channel)
        if len(lookup) == 0:
            lookup = await ModmailThreads.get_by(mod_thread=source_channel)
        mod_thread = self.bot.get_channel(lookup[0].mod_thread)
        user_thread = self.bot.get_channel(lookup[0].user_thread)
        guild = user_thread.guild

        to_send = message_content
        embed = discord.Embed(
            title="New Message",
            description=to_send[:2047],
            timestamp=datetime.datetime.utcnow(),
        )
        if len(to_send) > 2047:
            embed.add_field(name="Message (continued)", value=to_send[2048:3071])
        if len(to_send) > 3071:
            embed.add_field(name="Message (continued)", value=to_send[3072:4000])
        embed.set_footer(text=f"{guild.name} | {guild.id}", icon_url=guild.icon.url if guild.icon is not None else None)
        files = []
        files2 = []
        for file in received_files:
            saved_file = io.BytesIO()
            await file.save(saved_file)
            files.append(discord.File(saved_file, file.filename))

            saved_file2 = io.BytesIO()
            await file.save(saved_file2)
            files2.append(discord.File(saved_file2, file.filename))
        await mod_thread.send(files=files, embed=embed)
        await user_thread.send(files=files2, embed=embed)

    @command()
    async def reply(self, ctx: DozerContext, *, message):
        """Command to reply to a modmail thread."""
        # ensure this is a modmail thread
        lookup = await ModmailThreads.get_by(user_thread=ctx.channel.id)
        if len(lookup) == 0:
            lookup = await ModmailThreads.get_by(mod_thread=ctx.channel.id)
        if len(lookup) == 0:
            await ctx.reply("This command can only be used inside a modmail thread!")
            return

        await self.send_modmail_embeds(ctx.channel.id, message, ctx.message.attachments)
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
            await ctx.interaction.delete_original_response()

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
        target_record = await ModmailConfig.get_by(guild_id=ctx.guild.id)
        if len(target_record) == 0:
            await ctx.reply("Modmail is not configured for this server!")
            return
        view = Buttons()
        await ctx.send("Click the button to start a new modmail thread!", view=view)


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


class ModmailThreads(db.DatabaseTable):
    """Holds threads for modmail"""
    __tablename__ = "modmail_threads"
    __uniques__ = "user_thread, mod_thread"

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            user_thread bigint NOT NULL,
            mod_thread bigint NOT NULL,
            PRIMARY KEY (user_thread, mod_thread)
            )""")

    def __init__(self, user_thread: int, mod_thread: int):
        super().__init__()
        self.user_thread = user_thread
        self.mod_thread = mod_thread

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = ModmailThreads(user_thread=result.get("user_thread"), mod_thread=result.get("mod_thread"))
            result_list.append(obj)
        return result_list


modmail_cog = None


async def setup(bot):
    """Adds the modmail cog to the bot."""
    bot.add_view(Buttons())
    global modmail_cog
    modmail_cog = Modmail(bot)
    await bot.add_cog(modmail_cog)
