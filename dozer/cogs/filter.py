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

    """Helper Functions"""

    async def check_dm_filter(self, ctx, embed):
        """Send an embed, if the setting in the DB allows for it"""
        with db.Session() as session:
            results = session.query(WordFilterSetting).filter_by(guild_id=ctx.guild.id, setting_type="dm") \
                .one_or_none()

            if results is None:
                results = True
            else:
                results = results.value

            if results == "1":
                await ctx.author.send(embed=embed)
                await ctx.message.add_reaction("📬")
            else:
                await ctx.send(embed=embed)

    def load_filters(self, guild_id):
        """Load all filters for a selected guild """
        with db.Session() as session:
            results = session.query(WordFilter).filter_by(guild_id=guild_id, enabled=True).all()
            self.filter_dict[guild_id] = {}
            for wordfilter in results:
                self.filter_dict[guild_id][wordfilter.id] = re.compile(wordfilter.pattern, re.IGNORECASE)

    async def check_filters(self, message):
        """Check all the filters for a certain message (with it's guild)"""
        if message.author.id == self.bot.user.id:
            return
        with db.Session() as session:
            roles = session.query(WordFilterRoleWhitelist).filter_by(guild_id=message.guild.id).all()
        whitelisted_ids = set(role.role_id for role in roles)
        if any(x.id in whitelisted_ids for x in message.author.roles):
            return
        try:
            filters = self.filter_dict[message.guild.id]
        except KeyError:
            self.load_filters(message.guild.id)
            filters = self.filter_dict[message.guild.id]
        deleted = False
        for wordid, wordfilter in filters.items():
            if wordfilter.search(message.content) is not None:
                await message.channel.send("{}, Banned word detected!".format(message.author.mention), delete_after=5.0)
                time = datetime.datetime.utcnow()
                with db.Session() as session:
                    infraction = WordFilterInfraction(member_id=message.author.id, filter_id=wordid,
                                                      timestamp=time,
                                                      message=message.content)
                    session.add(infraction)
                if not deleted:
                    await message.delete()
                    deleted = True

    """Event Handlers"""

    async def on_message(self, message):
        """Send the message handler out"""
        await self.check_filters(message)

    async def on_message_edit(self, _, after):
        """Send the message handler out, but for edits"""
        await self.check_filters(after)

    """Commands"""

    @group(invoke_without_command=True)
    @guild_only()
    async def filter(self, ctx, advanced: bool = False):
        """List and manage filtered words"""
        with db.Session() as session:
            results = session.query(WordFilter).filter_by(guild_id=ctx.guild.id, enabled=True).all()
        if not results:
            embed = discord.Embed(title="Filters for {}".format(ctx.guild.name))
            embed.description = "No filters found for this guild! Add one using `{}whitelist add filter <>`".format(
                ctx.bot.command_prefix)
            embed.color = discord.Color.red()
            await ctx.send(embed=embed)
            return

        fmt = 'ID {0.id}: `{0.friendly_name}`'
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
        with db.Session() as session:
            session.add(new_filter)
        embed = discord.Embed()
        embed.title = "Filter {} added".format(new_filter.id)
        embed.description = "A new filter with the name `{}` was added.".format(friendly_name or pattern)
        embed.add_field(name="Pattern", value="`{}`".format(pattern))
        await ctx.send(embed=embed)
        self.load_filters(ctx.guild.id)

    add.example_usage = "`{prefix}filter whitelist add Swear` - Makes it so that \"Swear\" will be filtered"

    @guild_only()
    @has_permissions(manage_guild=True)
    @filter.command()
    async def remove(self, ctx, filter_id):
        """Remove a pattern from the filter list."""
        with db.Session() as session:
            result = session.query(WordFilter).filter_by(id=filter_id).one_or_none()
            if result is None:
                await ctx.send("Filter ID {} not found!".format(filter_id))
                return
            if result.guild_id != ctx.guild.id:
                await ctx.send("That Filter does not belong to this guild.")
                return
            result.enabled = False
        await ctx.send("Filter `{}` with name `{}` deleted.".format(result.id, result.friendly_name))
        self.load_filters(ctx.guild.id)

    remove.example_usage = "`{prefix}filter remove 7` - Disables filter with ID 7"

    @guild_only()
    @has_permissions(manage_guild=True)
    @filter.command(name="dm")
    async def dm_config(self, ctx, config: bool):
        """Set whether filter words should be DMed when used in bot messages"""
        with db.Session() as session:
            result = session.query(WordFilterSetting).filter_by(guild_id=ctx.guild.id, setting_type="dm") \
                .one_or_none()
            try:
                before_setting = result.value
                result.value = config
            except AttributeError:
                before_setting = None
                result = WordFilterSetting(guild_id=ctx.guild.id, setting_type="dm", value=config)
                session.add(result)
            await ctx.send(
                "The DM setting for this guild has been changed from {} to {}.".format(before_setting == "1",
                                                                                       result.value))

    dm_config.example_usage = "`{prefix}filter dm_config True` - Makes all messages containining filter lists to be sent through DMs"

    @guild_only()
    @filter.group(invoke_without_command=True)
    async def whitelist(self, ctx):
        """List all whitelisted roles for this server"""
        with db.Session() as session:
            results = session.query(WordFilterRoleWhitelist).filter_by(guild_id=ctx.guild.id).all()
            role_objects = (ctx.guild.get_role(db_role.role_id) for db_role in results)
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
        with db.Session() as session:
            result = session.query(WordFilterRoleWhitelist).filter_by(role_id=role.id).one_or_none()
            if result is not None:
                await ctx.send("That role is already whitelisted.")
                return
            whitelist_entry = WordFilterRoleWhitelist(guild_id=ctx.guild.id, role_id=role.id)
            session.add(whitelist_entry)
        await ctx.send("Whitelisted `{}` for this guild.".format(role.name))

    whitelist_add.example_usage = "`{prefix}filter whitelist add Moderators` - Makes it so that Moderators will not be caught by the filter."

    @guild_only()
    @has_permissions(manage_roles=True)
    @whitelist.command(name="remove")
    async def whitelist_remove(self, ctx, *, role: discord.Role):
        """Remove a role from the whitelist"""
        with db.Session() as session:
            result = session.query(WordFilterRoleWhitelist).filter_by(role_id=role.id).one_or_none()
            if result is None:
                await ctx.send("That role is not whitelisted.")
                return
            session.delete(result)
        await ctx.send("The role `{}` is no longer whitelisted.".format(role.name))

    whitelist_remove.example_usage = "`{prefix}filter whitelist remove Admins` - Makes it so that Admins are caught by the filter again."


def setup(bot):
    """Setup cog"""
    bot.add_cog(Filter(bot))


"""Database Tables"""


class WordFilter(db.DatabaseObject):
    """Object for each filter"""
    __tablename__ = "word_filters"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    enabled = db.Column(db.Boolean, default=True)
    guild_id = db.Column(db.BigInteger)
    friendly_name = db.Column(db.String, nullable=True)
    pattern = db.Column(db.String)
    infractions = db.relationship("WordFilterInfraction", back_populates="filter")


class WordFilterSetting(db.DatabaseObject):
    """Each filter-related setting (will be replaced soon)"""
    __tablename__ = "word_filter_settings"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    setting_type = db.Column(db.String)
    guild_id = db.Column(db.BigInteger)
    value = db.Column(db.String)


class WordFilterRoleWhitelist(db.DatabaseObject):
    """Object for each whitelisted role (guild-specific)"""
    __tablename__ = "word_filter_role_whitelist"
    guild_id = db.Column(db.Integer)
    role_id = db.Column(db.BigInteger, primary_key=True)


class WordFilterInfraction(db.DatabaseObject):
    """Object for each word filter infraction"""
    __tablename__ = "word_filter_infraction"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    member_id = db.Column(db.BigInteger)
    filter_id = db.Column(db.Integer, db.ForeignKey('word_filters.id'))
    filter = db.relationship("WordFilter", back_populates="infractions")
    timestamp = db.Column(db.DateTime)
    message = db.Column(db.String)
