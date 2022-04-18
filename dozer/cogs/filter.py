"""Establish a system of filters that allow run-time specified filters to applied to all messages in a guild,
with whitelisted role exceptions."""

import datetime
import re
import discord
from discord.ext.commands import guild_only, has_permissions

from ._utils import *
from .. import db


class Filter(Cog):
    """The filters need to be compiled each time they're run, but we don't want to compile every filter
    Every time it's run, or all of them at once when the bot starts. So the first time that filter is run,
    the compiled object is placed in here. This dict is actually a dict full of dicts, with each parent dict's key
    being the guild ID for easy accessing.
    """
    filter_dict = {}

    def __init__(self, bot):
        super().__init__(bot)
        self.word_filter_setting = db.ConfigCache(WordFilterSetting)
        self.word_filter_role_whitelist = db.ConfigCache(WordFilterRoleWhitelist)

    """Helper Functions"""

    async def check_dm_filter(self, ctx, embed):
        """Send an embed, if the setting in the DB allows for it"""
        results = await WordFilterSetting.get_by(guild_id=ctx.guild.id, setting_type="dm")
        if results:
            result = results[0].value
        else:
            result = "1"

        if result == "1":
            await ctx.author.send(embed=embed)
            await ctx.message.add_reaction("📬")
        else:
            await ctx.send(embed=embed)

    async def load_filters(self, guild_id):
        """Load all filters for a selected guild """
        results = await WordFilter.get_by(guild_id=guild_id, enabled=True)
        self.filter_dict[guild_id] = {}
        for wordfilter in results:
            self.filter_dict[guild_id][wordfilter.filter_id] = re.compile(wordfilter.pattern, re.IGNORECASE)

    async def check_filters_messages(self, message):
        """Check all the filters for a certain message (with it's guild)"""
        if message.author.id == self.bot.user.id or not hasattr(message.author, 'roles'):
            return
        roles = await self.word_filter_role_whitelist.query_all(guild_id=message.guild.id)
        whitelisted_ids = set(role.role_id for role in roles)
        if any(x.id in whitelisted_ids for x in message.author.roles):
            return
        try:
            filters = self.filter_dict[message.guild.id]
        except KeyError:
            await self.load_filters(message.guild.id)
            filters = self.filter_dict[message.guild.id]
        deleted = False
        for wordid, wordfilter in filters.items():
            if wordfilter.search(message.content) is not None:
                await message.channel.send(f"{message.author.mention}, Banned word detected!", delete_after=5.0)
                if not deleted:
                    await message.delete()
                    deleted = True

    async def check_filters_nicknames(self, member_before, member_after):
        """Check all filters for a members nickname change"""
        if member_after.id == self.bot.user.id or not hasattr(member_after, 'roles'):
            return
        roles = await self.word_filter_role_whitelist.query_all(guild_id=member_after.guild.id)
        whitelisted_ids = set(role.role_id for role in roles)
        if any(x.id in whitelisted_ids for x in member_after.roles):
            return
        try:
            filters = self.filter_dict[member_after.guild.id]
        except KeyError:
            await self.load_filters(member_after.guild.id)
            filters = self.filter_dict[member_after.guild.id]
        reverted = False
        if member_after.nick is None:
            return
        for wordid, wordfilter in filters.items():
            if wordfilter.search(member_after.nick) is not None:
                if not reverted:
                    try:
                        await member_after.edit(nick=member_before.nick)
                        await member_after.send(f"{member_after.mention}, your nickname in **{member_after.guild}** "
                                                f"contained a banned word and has been reset to your previous nickname")
                    except discord.Forbidden:
                        await member_after.send(f"{member_after.mention}, your nickname in **{member_after.guild}** "
                                                f"contains a banned word but because your permissions outrank dozer "
                                                f"it was not reset")
                    reverted = True

    """Event Handlers"""

    @Cog.listener('on_message')
    async def on_message(self, message):
        """Send the message handler out"""
        await self.check_filters_messages(message)

    @Cog.listener('on_message_edit')
    async def on_message_edit(self, _, after):
        """Send the message handler out, but for edits"""
        await self.check_filters_messages(after)

    @Cog.listener("on_member_update")
    async def on_member_update(self, before, after):
        """Called whenever a member gets updated"""
        if before.nick != after.nick:
            await self.check_filters_nicknames(before, after)

    """Commands"""

    @group(invoke_without_command=True)
    @guild_only()
    async def filter(self, ctx, advanced: bool = False):
        """List and manage filtered words"""
        results = await WordFilter.get_by(guild_id=ctx.guild.id, enabled=True)

        if not results:
            embed = discord.Embed(title="Filters for {}".format(ctx.guild.name))
            embed.description = "No filters found for this guild! Add one using `{}filter add <regex> [name]`".format(
                ctx.prefix)
            embed.color = discord.Color.red()
            await ctx.send(embed=embed)
            return

        fmt = 'ID {0.filter_id}: `{0.friendly_name}`'
        if advanced:
            fmt += ': Pattern: `{0.pattern}`'

        filter_text = '\n'.join(map(fmt.format, results))

        embed = discord.Embed()
        embed.title = "Filters for {}".format(ctx.guild.name)
        embed.add_field(name="Filters", value=filter_text)
        embed.color = discord.Color.dark_orange()
        await self.check_dm_filter(ctx, embed)

    filter.example_usage = """`{prefix}filter add test` - Adds test as a filter.
    `{prefix}filter remove 1` - Removes filter 1
    `{prefix}filter dm true` - Any messages containing a filtered word will be DMed
    `{prefix}filter whitelist` - See all of the whitelisted roles
    `{prefix}filter whitelist add Administrators` - Make the Administrators role whitelisted for the filter.
    `{prefix}filter whitelist remove Moderators` - Make the Moderators role no longer whitelisted."""

    @guild_only()
    @has_permissions(manage_guild=True)
    @filter.command()
    async def add(self, ctx, pattern, friendly_name=None):
        """Add a pattern to the filter using RegEx. Any word can be added and is tested case-insensitive."""
        try:
            re.compile(pattern)
        except re.error as err:
            await ctx.send("Invalid RegEx! ```{}```".format(err.msg))
            return
        new_filter = WordFilter(guild_id=ctx.guild.id, pattern=pattern, friendly_name=friendly_name or pattern)
        await new_filter.update_or_add()
        embed = discord.Embed()
        embed.title = "Filter added!"
        embed.description = "A new filter with the name `{}` was added.".format(friendly_name or pattern)
        embed.add_field(name="Pattern", value="`{}`".format(pattern))
        await ctx.send(embed=embed)
        await self.load_filters(ctx.guild.id)

    add.example_usage = "`{prefix}filter add Swear` - Makes it so that \"Swear\" will be filtered"

    @guild_only()
    @has_permissions(manage_guild=True)
    @filter.command()
    async def edit(self, ctx, filter_id: int, pattern):
        """Edit an already existing filter using a new pattern. A filter's friendly name cannot be edited."""
        try:
            re.compile(pattern)
        except re.error as err:
            await ctx.send("Invalid RegEx! ```{}```".format(err.msg))
            return
        results = await WordFilter.get_by(guild_id=ctx.guild.id)
        found = False
        result = None
        for result in results:
            if result.filter_id == filter_id:
                found = True
                break
        if not found:
            await ctx.send("That filter ID does not exist or does not belong to this guild.")
            return
        old_pattern = result.pattern
        enabled_change = False
        if not result.enabled:
            result.enabled = True
            enabled_change = True
        result.pattern = pattern
        await result.update_or_add()
        await self.load_filters(ctx.guild.id)
        embed = discord.Embed(title="Updated filter {}".format(result.friendly_name or result.pattern))
        embed.description = "Filter ID {} has been updated.".format(result.filter_id)
        embed.add_field(name="Old Pattern", value=old_pattern)
        embed.add_field(name="New Pattern", value=pattern)
        if enabled_change:
            embed.add_field(name="Enabled Change", value="This filter was disabled prior to editing, so it has been "
                                                         "re-enabled due to being edited.")
        await ctx.send(embed=embed)

    edit.example_usage = "`{prefix}filter edit 4 Swear` - Change filter 4 to filter out \"Swear\" instead of its " \
                         "previous pattern"

    @guild_only()
    @has_permissions(manage_guild=True)
    @filter.command()
    async def remove(self, ctx, filter_id: int):
        """Remove a pattern from the filter list."""
        result = await WordFilter.get_by(filter_id=filter_id)
        if len(result) == 0:
            await ctx.send("Filter ID {} not found!".format(filter_id))
            return
        else:
            result = result[0]
        if result.guild_id != ctx.guild.id:
            await ctx.send("That Filter does not belong to this guild.")
            return
        result.enabled = False
        await result.update_or_add()
        await ctx.send("Filter with name `{}` deleted.".format(result.friendly_name))
        await self.load_filters(ctx.guild.id)

    remove.example_usage = "`{prefix}filter remove 7` - Disables filter with ID 7"

    @guild_only()
    @has_permissions(manage_guild=True)
    @filter.command(name="dm")
    async def dm_config(self, ctx, config: bool):
        """Set whether filter words should be DMed when used in bot messages"""
        config = str(int(config)) # turns into "1" or "0" idk man
        results = await WordFilterSetting.get_by(guild_id=ctx.guild.id, setting_type="dm")
        if results:
            before_setting = results[0].value
            # Due to the settings table having a serial ID, inserts always succeed, so update_or_add can't be used to
            # update in place. Instead we have to delete and reinsert the record.
            await WordFilterSetting.delete(guild_id=results[0].guild_id, setting_type=results[0].setting_type)
        else:
            before_setting = None
        result = WordFilterSetting(guild_id=ctx.guild.id, setting_type="dm", value=config)
        await result.update_or_add()
        self.word_filter_setting.invalidate_entry(guild_id=ctx.guild.id, setting_type="dm")
        await ctx.send(
            "The DM setting for this guild has been changed from {} to {}.".format(before_setting == "1", result.value == "1"))

    dm_config.example_usage = "`{prefix}filter dm_config True` - Makes all messages containining filter lists to be sent through DMs"

    @guild_only()
    @filter.group(invoke_without_command=True)
    async def whitelist(self, ctx):
        """List all whitelisted roles for this server"""
        results = await WordFilterRoleWhitelist.get_by(guild_id=ctx.guild.id)
        role_objects = [ctx.guild.get_role(db_role.role_id) for db_role in results]
        role_names = (role.name for role in role_objects if role is not None)
        roles_text = "\n".join(role_names)
        embed = discord.Embed()
        embed.title = "Whitelisted roles for {}".format(ctx.guild.name)
        embed.description = "Anybody with any of the roles below will not have their messages filtered."
        embed.add_field(name="Roles", value=roles_text or "No roles")
        await ctx.send(embed=embed)

    whitelist.example_usage = "`{prefix}filter whitelist` - Lists all the whitelisted roles"

    @guild_only()
    @has_permissions(manage_roles=True)
    @whitelist.command(name="add")
    async def whitelist_add(self, ctx, *, role: discord.Role):
        """Add a role to the whitelist"""
        result = await WordFilterRoleWhitelist.get_by(role_id=role.id)
        if len(result) != 0:
            await ctx.send("That role is already whitelisted.")
            return
        whitelist_entry = WordFilterRoleWhitelist(role_id=role.id, guild_id=ctx.guild.id)
        await whitelist_entry.update_or_add()
        self.word_filter_role_whitelist.invalidate_entry(guild_id=ctx.guild.id)
        await ctx.send("Whitelisted `{}` for this guild.".format(role.name))

    whitelist_add.example_usage = "`{prefix}filter whitelist add Moderators` - Makes it so that Moderators will not be caught by the filter."

    @guild_only()
    @has_permissions(manage_roles=True)
    @whitelist.command(name="remove")
    async def whitelist_remove(self, ctx, *, role: discord.Role):
        """Remove a role from the whitelist"""
        result = await WordFilterRoleWhitelist.get_by(role_id=role.id)
        if len(result) == 0:
            await ctx.send("That role is not whitelisted.")
            return
        await WordFilterRoleWhitelist.delete(role_id=role.id)
        self.word_filter_role_whitelist.invalidate_entry(guild_id=ctx.guild.id)
        await ctx.send("The role `{}` is no longer whitelisted.".format(role.name))

    whitelist_remove.example_usage = "`{prefix}filter whitelist remove Admins` - Makes it so that Admins are caught by the filter again."


def setup(bot):
    """Setup cog"""

    bot.add_cog(Filter(bot))


"""Database Tables"""


class WordFilter(db.DatabaseTable):
    """Object for each filter"""
    __tablename__ = 'word_filters'
    __uniques__ = 'filter_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            filter_id serial PRIMARY KEY NOT NULL,
            enabled boolean default true NOT NULL,
            guild_id bigint NOT NULL,
            friendly_name varchar null,
            pattern varchar NOT NULL
            )""")

    def __init__(self, guild_id, friendly_name, pattern, enabled=True, filter_id=None):
        super().__init__()
        self.filter_id = filter_id
        self.guild_id = guild_id
        self.enabled = enabled
        self.friendly_name = friendly_name
        self.pattern = pattern

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = WordFilter(guild_id=result.get("guild_id"), friendly_name=result.get("friendly_name"),
                             pattern=result.get("pattern"), enabled=result.get("enabled"), filter_id=result.get("filter_id"))
            result_list.append(obj)
        return result_list


class WordFilterSetting(db.DatabaseTable):
    """Each filter-related setting"""
    __tablename__ = 'word_filter_settings'
    __uniques__ = 'id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            id serial PRIMARY KEY NOT NULL,
            setting_type varchar NOT NULL,
            guild_id bigint NOT NULL,
            value varchar NOT NULL
            )""")

    def __init__(self, guild_id, setting_type, value):
        super().__init__()
        self.guild_id = guild_id
        self.setting_type = setting_type
        self.value = value

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = WordFilterSetting(guild_id=result.get("guild_id"), setting_type=result.get("setting_type"),
                                    value=result.get('value'))
            result_list.append(obj)
        return result_list


class WordFilterRoleWhitelist(db.DatabaseTable):
    """Object for each whitelisted role"""
    __tablename__ = 'word_filter_role_whitelist'
    __uniques__ = 'role_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint NOT NULL,
            role_id bigint PRIMARY KEY NOT NULL 
            )""")

    def __init__(self, guild_id, role_id):
        super().__init__()
        self.role_id = role_id
        self.guild_id = guild_id

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = WordFilterRoleWhitelist(guild_id=result.get("guild_id"), role_id=result.get("role_id"))
            result_list.append(obj)
        return result_list
