"""Adds simple text-shortcuts to the bot"""

import discord
from discord.ext import commands
from discord.ext.commands import BadArgument, guild_only, has_permissions
from fuzzywuzzy import process, fuzz

from dozer.context import DozerContext
from ._utils import *
from .. import db
from ..db import *

class Shortcuts(Cog):
    """Adds simple text-shortcuts to the bot"""
    MAX_LEN = 20
    def __init__(self, bot):
        """cog init"""
        super().__init__(bot)
        self.settings_cache = db.ConfigCache(ShortcutSetting)
        self.cache = db.ConfigCache(ShortcutEntry)

    """Commands for managing shortcuts/macros."""
    @guild_only()
    @has_permissions(manage_messages=True)
    @group(invoke_without_command=True)
    async def shortcuts(self, ctx):
        """
        Display shortcut information
        """
        settings: ShortcutSetting = await self.settings_cache.query_one(guild_id=ctx.guild.id)

        if settings is None:
            raise BadArgument("This server has no shortcut configuration, set a prefix.")

        e = discord.Embed()
        e.title = "Server shortcut configuration"
        e.add_field(name="Shortcut prefix", value=settings.prefix or "[unset]")
        await ctx.send(embed=e)

    @guild_only()
    @has_permissions(manage_messages=True)
    @shortcuts.command()
    async def setprefix(self, ctx, prefix):
        """Set the prefix to be used to respond to shortcuts for the server."""
        setting: ShortcutSetting = await self.settings_cache.query_one(guild_id=ctx.guild.id)

        if setting:
            setting.prefix = prefix
        else:
            setting = ShortcutSetting(guild_id=ctx.guild.id, prefix=prefix)

        await setting.update_or_add()
        self.settings_cache.invalidate_entry(guild_id=ctx.guild.id)

        await ctx.send(f"Set prefix to: {prefix}")

    @guild_only()
    @has_permissions(manage_messages=True)
    @shortcuts.command(aliases=["add"])
    async def set(self, ctx, cmd_name, *, cmd_msg):
        """Set the message to be sent for a given shortcut name."""
        settings: ShortcutSetting = await self.settings_cache.query_one(guild_id=ctx.guild.id)
        if settings is None:
            raise BadArgument("Set a prefix first!")
        if len(cmd_name) > self.MAX_LEN:
            raise BadArgument(f"command names can only be up to {self.MAX_LEN} chars long")
        if not cmd_msg:
            raise BadArgument("can't have null message")

        ent: ShortcutEntry = await self.cache.query_one(guild_id=ctx.guild.id, name=cmd_name)

        if ent:
            ent.value = cmd_msg
        else:
            ent = ShortcutEntry(guild_id=ctx.guild.id, name=cmd_name, value=cmd_msg)

        await ent.update_or_add()
        self.cache.invalidate_entry(guild_id=ctx.guild.id, name=cmd_name)

        await ctx.send("Updated command successfully.")

    set.example_usage = """
    `{prefix}shortcuts set hello Hello, World!!!!` - set !hello for the server
    """

    @guild_only()
    @has_permissions(manage_messages=True)
    @shortcuts.command()
    async def remove(self, ctx, cmd_name):
        """Removes a shortcut from the server by name."""
        ent: ShortcutEntry = await self.cache.query_one(guild_id=ctx.guild.id, name=cmd_name)

        if ent:
            await ShortcutEntry.delete(guild_id=ctx.guild.id, name=cmd_name)
            self.cache.invalidate_entry(guild_id=ctx.guild.id, name=cmd_name)
            await ctx.send(f"Removed command {cmd_name} successfully.")
        else:
            await ctx.send(f"No command named {cmd_name} found!")

    remove.example_usage = """
    `{prefix}shortcuts remove hello  - removes !hello
    """

    @guild_only()
    @shortcuts.command()
    async def list(self, ctx):
        """Lists all shortcuts for the server."""
        settings: ShortcutSetting = await self.settings_cache.query_one(guild_id=ctx.guild.id)

        ents: List[ShortcutEntry] = await ShortcutEntry.get_by(guild_id=ctx.guild.id)

        if not ents:
            await ctx.send("No shortcuts for this server!")
            return

        embed = None
        for i, e in enumerate(ents):
            if i % 20 == 0:
                if embed is not None:
                    await ctx.send(embed=embed)
                embed = discord.Embed()
                embed.title = "Shortcuts for this server"
            embed.add_field(name=settings.prefix + e.name, value=e.value[:1024])

        if embed.fields:
            await ctx.send(embed=embed)

    list.example_usage = """
    `{prefix}shortcuts list - lists all shortcuts
    """

    @Cog.listener()
    async def on_message(self, msg: discord.Message):
        """prefix scanner"""
        if not msg.guild or msg.author.bot:
            return

        setting = await ShortcutSetting.get_unique_by(guild_id = msg.guild.id)
        if not setting:
            return

        # Search for the prefix within the message content
        prefix = setting.prefix
        prefix_index = msg.content.find(prefix)


        if prefix_index != -1:
            # before running any chatgpt stuff, check if there's a space between prefix and shortcut
            if prefix_index + len(prefix) < len(msg.content) and msg.content[prefix_index + len(prefix)] == ' ':
                return  # there's a space, so it was probably meant to be used in text rather than call a shortcut
            # Extract the word immediately after the prefix
            start_index = prefix_index + len(prefix)
            remaining_content = msg.content[start_index:].strip()
            first_word = remaining_content.split()[0] if remaining_content else ''

            # Check if the first word is a valid command name
            all_shortcuts = await ShortcutEntry.get_by(guild_id=msg.guild.id)
            all_shortcuts = [s.name for s in all_shortcuts]

            best_match = process.extractOne(first_word, all_shortcuts, scorer=fuzz.partial_ratio)

            if best_match and best_match[1] > 80:  # Adjust the threshold as needed
                shortcut_name = best_match[0]

                shortcut = await ShortcutEntry.get_unique_by(guild_id=msg.guild.id, name=shortcut_name)
                if msg.reference:
                    # Fetch the original message being replied to
                    original_message = await msg.channel.fetch_message(msg.reference.message_id)
                    if original_message:
                        # Ping the original author in the new message
                        await original_message.reply(f"{shortcut.value}")
                else:
                    # Send the shortcut value without pinging if original message is not found
                    await msg.channel.send(shortcut.value)
        else:
            # If the prefix is not found in the message, do nothing
            pass

async def setup(bot):
    """Adds the shortcuts cog to the main bot project."""
    await bot.add_cog(Shortcuts(bot))


"""Database Tables"""


class ShortcutSetting(db.DatabaseTable):
    """Provides a DB config to track shortcut setting per guild."""
    __tablename__ = 'shortcut_settings'
    __uniques__ = "guild_id"

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY NOT NULL,
            prefix varchar NOT NULL
            )""")

    def __init__(self, guild_id: int, prefix: str):
        super().__init__()
        self.guild_id = guild_id
        self.prefix = prefix

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = ShortcutSetting(guild_id=result.get("guild_id"), prefix=result.get("prefix"))
            result_list.append(obj)
        return result_list

class ShortcutEntry(db.DatabaseTable):
    """Provides a DB config to track shortcut entries."""
    __tablename__ = 'shortcuts'
    __uniques__ = 'guild_id, name'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint NOT NULL,
            name varchar NOT NULL,
            value text NOT NULL,
            PRIMARY KEY (guild_id, name)
            )""")

    def __init__(self, guild_id: int, name: str, value: str):
        super().__init__()
        self.guild_id = guild_id
        self.name = name
        self.value = value

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = ShortcutEntry(guild_id=result.get("guild_id"),
                                name=result.get("name"),
                                value=result.get("value"))
            result_list.append(obj)
        return result_list
