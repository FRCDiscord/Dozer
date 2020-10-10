"""Role management commands."""
import asyncio
import time

import discord
import discord.utils
from discord.ext.commands import cooldown, BucketType, has_permissions, BadArgument
from ..db import *

from ._utils import *
from .. import db

blurple = discord.Color.blurple()


class Roles(Cog):
    """Commands for role management."""

    def __init__(self, bot):
        super().__init__(bot)
        for command in self.giveme.walk_commands():
            @command.before_invoke
            async def givemeautopurge(self, ctx):
                """Before invoking a giveme command, run a purge"""
                if await self.ctx_purge(ctx):
                    await ctx.send("Purged missing roles")

    @staticmethod
    def calculate_epoch_time(time_string):
        seconds_per_unit = {"m": 60, "h": 3600, "d": 86400, "w": 604800, "y": 3.154e+7}
        time_delta = int(time_string[:-1]) * seconds_per_unit[time_string[-1]]
        time_release = round(time.time() + abs(time_delta))
        return time_release

    @Cog.listener('on_ready')
    async def on_ready(self):
        """Restore tempRole timers on bot startup"""
        q = await TempRoleTimerRecords.get_by()  # no filters: all
        for r in q:
            self.bot.loop.create_task(self.removal_timer(r))

    async def removal_timer(self, r):
        """Asynchronous task that sleeps for a set time to remove a role from a member after a set period of time."""

        guild = self.bot.get_guild(int(r.guild_id))
        # actor = self.bot.get_member(int(r.actor_id))
        #target = await guild.fetch_member(int(r.target_id))
        target = guild.get_member(int(r.actor_id))
        target_role = guild.get_role(int(r.target_role_id))
        removal_time = r.removal_ts

        print(target)

        time_delta = max(int(removal_time - time.time()), 1)

        await asyncio.sleep(time_delta)

        await target.remove_roles(target_role)

        await TempRoleTimerRecords.delete(id=r.id)



    @Cog.listener('on_member_join')
    async def on_member_join(self, member):
        """Restores a member's roles when they join if they have joined before."""
        me = member.guild.me
        top_restorable = me.top_role.position if me.guild_permissions.manage_roles else 0
        restore = await MissingRole.get_by(guild_id=member.guild.id, member_id=member.id)
        if len(restore) == 0:
            return  # New member - nothing to restore

        valid, cant_give, missing = set(), set(), set()
        for missing_role in restore:
            role = member.guild.get_role(missing_role.role_id)
            if role is None:  # Role with that ID does not exist
                missing.add(missing_role.role_name)
            elif role.position > top_restorable:
                cant_give.add(role.name)
            else:
                valid.add(role)
        for entry in restore:
            # Not missing anymore - remove the record to free up the primary key
            await MissingRole.delete(role_id=entry.role_id, member_id=entry.member_id)

        await member.add_roles(*valid)
        if not missing and not cant_give:
            return

        e = discord.Embed(title='Welcome back to the {} server, {}!'.format(member.guild.name, member),
                          color=discord.Color.blue())
        if missing:
            e.add_field(name='I couldn\'t restore these roles, as they don\'t exist.', value='\n'.join(sorted(missing)))
        if cant_give:
            e.add_field(name='I couldn\'t restore these roles, as I don\'t have permission.',
                        value='\n'.join(sorted(cant_give)))

        send_perms = discord.Permissions()
        send_perms.update(send_messages=True, embed_links=True)
        try:
            dest = next(channel for channel in member.guild.text_channels if channel.permissions_for(me) >= send_perms)
        except StopIteration:
            dest = await member.guild.owner.create_dm()

        await dest.send(embed=e)

    @Cog.listener('on_member_remove')
    async def on_member_remove(self, member):
        """Saves a member's roles when they leave in case they rejoin."""
        guild_id = member.guild.id
        member_id = member.id
        for role in member.roles[1:]:  # Exclude the @everyone role
            db_member = MissingRole(role_id=role.id, role_name=role.name, guild_id=guild_id, member_id=member_id)
            await db_member.update_or_add()

    async def giveme_purge(self, rolelist):
        """Purges roles in the giveme database that no longer exist. The argument is a list of GiveableRole objects."""
        for role in rolelist:
            dbrole = await GiveableRole.get_by(role_id=role.role_id)
            if dbrole:
                await GiveableRole.delete(role_id=role.role_id)

    async def ctx_purge(self, ctx):
        """Purges all giveme roles that no longer exist in a guild"""
        counter = 0
        roles = await GiveableRole.get_by(guild_id=ctx.guild.id)
        guildroles = []
        rolelist = []
        for i in ctx.guild.roles:
            guildroles.append(i.id)
        for role in roles:
            if role.role_id not in guildroles:
                rolelist.append(role)
                counter += 1
        await self.giveme_purge(rolelist)
        return counter

    async def on_guild_role_delete(self, role):
        """Automatically delete giveme roles if they are deleted from the guild"""
        rolelist = [role]
        await self.giveme_purge(rolelist)

    @group(invoke_without_command=True)
    @bot_has_permissions(manage_roles=True)
    async def giveme(self, ctx, *, roles):
        """Give you one or more giveable roles, separated by commas."""
        norm_names = [self.normalize(name) for name in roles.split(',')]
        giveable_ids = [tup.role_id for tup in await GiveableRole.get_by(guild_id=ctx.guild.id) if
                        tup.norm_name in norm_names]
        valid = set(role for role in ctx.guild.roles if role.id in giveable_ids)

        already_have = valid & set(ctx.author.roles)
        given = valid - already_have
        await ctx.author.add_roles(*given)

        e = discord.Embed(color=discord.Color.blue())
        if given:
            given_names = sorted((role.name for role in given), key=str.casefold)
            e.add_field(name='Gave you {} role(s)!'.format(len(given)), value='\n'.join(given_names), inline=False)
        if already_have:
            already_have_names = sorted((role.name for role in already_have), key=str.casefold)
            e.add_field(name='You already have {} role(s)!'.format(len(already_have)),
                        value='\n'.join(already_have_names), inline=False)
        extra = len(norm_names) - len(valid)
        if extra > 0:
            e.add_field(name='{} role(s) could not be found!'.format(extra),
                        value='Use `{0.prefix}{0.invoked_with} list` to find valid giveable roles!'.format(ctx),
                        inline=False)
        await ctx.send(embed=e)

    giveme.example_usage = """
    `{prefix}giveme Java` - gives you the role called Java, if it exists
    `{prefix}giveme Java, Python` - gives you the roles called Java and Python, if they exist
    """

    @giveme.command()
    @bot_has_permissions(manage_roles=True)
    @has_permissions(manage_roles=True)
    async def purge(self, ctx):
        """Force a purge of giveme roles that no longer exist in the guild"""
        counter = await self.ctx_purge(ctx)
        await ctx.send("Purged {} role(s)".format(counter))

    @giveme.command()
    @bot_has_permissions(manage_roles=True)
    @has_permissions(manage_guild=True)
    async def add(self, ctx, *, name):
        """Makes an existing role giveable, or creates one if it doesn't exist. Name must not contain commas.
        Similar to create, but will use an existing role if one exists."""
        if ',' in name:
            raise BadArgument('giveable role names must not contain commas!')
        norm_name = self.normalize(name)
        settings = await GiveableRole.get_by(guild_id=ctx.guild.id, norm_name=norm_name)
        if settings:
            raise BadArgument('that role already exists and is giveable!')
        candidates = [role for role in ctx.guild.roles if self.normalize(role.name) == norm_name]

        if not candidates:
            role = await ctx.guild.create_role(name=name, reason='Giveable role created by {}'.format(ctx.author))
        elif len(candidates) == 1:
            role = candidates[0]
        else:
            raise BadArgument('{} roles with that name exist!'.format(len(candidates)))
        await GiveableRole.from_role(role).update_or_add()
        await ctx.send(
            'Role "{0}" added! Use `{1}{2} {0}` to get it!'.format(role.name, ctx.prefix, ctx.command.parent))

    add.example_usage = """
    `{prefix}giveme add Java` - creates or finds a role named "Java" and makes it giveable
    `{prefix}giveme Java` - gives you the Java role that was just found or created
    """

    @giveme.command()
    @bot_has_permissions(manage_roles=True)
    @has_permissions(manage_guild=True)
    async def create(self, ctx, *, name):
        """Create a giveable role. Name must not contain commas.
        Similar to add, but will always create a new role."""
        if ',' in name:
            raise BadArgument('giveable role names must not contain commas!')
        norm_name = self.normalize(name)
        settings = await GiveableRole.get_by(guild_id=ctx.guild.id, norm_name=norm_name)
        if not settings:
            role = await ctx.guild.create_role(name=name, reason='Giveable role created by {}'.format(ctx.author))
            settings = GiveableRole.from_role(role)
            await settings.update_or_add()
            await ctx.send(
                'Role "{0}" created! Use `{1}{2} {0}` to get it!'.format(role.name, ctx.prefix, ctx.command.parent))

        else:
            raise BadArgument('that role already exists and is giveable!')

    create.example_usage = """
    `{prefix}giveme create Python` - creates a role named "Python" and makes it giveable
    `{prefix}giveme Python` - gives you the Python role that was just created
    """

    @giveme.command()
    @bot_has_permissions(manage_roles=True)
    async def remove(self, ctx, *, roles):
        """Removes multiple giveable roles from you. Names must be separated by commas."""
        norm_names = [self.normalize(name) for name in roles.split(',')]
        query = await GiveableRole.get_by(guild_id=ctx.guild.id)
        roles_to_remove = []
        for role in query:
            if role.norm_name in norm_names:
                roles_to_remove.append(role)
        removable_ids = [tup.role_id for tup in roles_to_remove]
        valid = set(role for role in ctx.guild.roles if role.id in removable_ids)

        removed = valid & set(ctx.author.roles)
        dont_have = valid - removed
        await ctx.author.remove_roles(*removed)

        e = discord.Embed(color=discord.Color.blue())
        if removed:
            removed_names = sorted((role.name for role in removed), key=str.casefold)
            e.add_field(name='Removed {} role(s)!'.format(len(removed)), value='\n'.join(removed_names), inline=False)
        if dont_have:
            dont_have_names = sorted((role.name for role in dont_have), key=str.casefold)
            e.add_field(name='You didn\'t have {} role(s)!'.format(len(dont_have)), value='\n'.join(dont_have_names),
                        inline=False)
        extra = len(norm_names) - len(valid)
        if extra > 0:
            e.add_field(name='{} role(s) could not be found!'.format(extra),
                        value='Use `{0.prefix}{0.invoked_with} list` to find valid giveable roles!'.format(ctx),
                        inline=False)
        await ctx.send(embed=e)

    remove.example_usage = """
    `{prefix}giveme remove Java` - removes the role called "Java" from you (if it can be given with `{prefix}giveme`)
    `{prefix}giveme remove Java, Python` - removes the roles called "Java" and "Python" from you
    """

    @giveme.command()
    @bot_has_permissions(manage_roles=True)
    @has_permissions(manage_guild=True)
    async def delete(self, ctx, *, name):
        """Deletes and removes a giveable role."""
        if ',' in name:
            raise BadArgument('this command only works with single roles!')
        norm_name = self.normalize(name)
        valid_ids = set(role.id for role in ctx.guild.roles)
        roles = await GiveableRole.get_by(guild_id=ctx.guild.id, norm_name=norm_name)
        valid_roles = []
        for role_option in roles:
            if role_option.role_id in valid_ids:
                valid_roles.append(role_option)
        if len(valid_roles) == 0:
            raise BadArgument('that role does not exist or is not giveable!')
        elif len(valid_roles) > 1:
            raise BadArgument('multiple giveable roles with that name exist!')
        else:
            role = ctx.guild.get_role(valid_roles[0].role_id)
            await GiveableRole.delete(guild_id=ctx.guild.id, norm_name=valid_roles[0].norm_name)
            await role.delete(reason='Giveable role deleted by {}'.format(ctx.author))
            await ctx.send('Role "{0}" deleted!'.format(role))

    delete.example_usage = """
    `{prefix}giveme delete Java` - deletes the role called "Java" if it's giveable (automatically removes it from all members)
    """

    @cooldown(1, 10, BucketType.channel)
    @giveme.command(name='list')
    @bot_has_permissions(manage_roles=True)
    async def list_roles(self, ctx):
        """Lists all giveable roles for this server."""
        names = [tup.name for tup in await GiveableRole.get_by(guild_id=ctx.guild.id)]
        e = discord.Embed(title='Roles available to self-assign', color=discord.Color.blue())
        e.description = '\n'.join(sorted(names, key=str.casefold))
        await ctx.send(embed=e)

    list_roles.example_usage = """
    `{prefix}giveme list` - lists all giveable roles
    """

    @staticmethod
    def normalize(name):
        """Normalizes a role for consistency in the DB."""
        return name.strip().casefold()

    @giveme.command()
    @bot_has_permissions(manage_roles=True)
    @has_permissions(manage_guild=True)
    async def removefromlist(self, ctx, *, name):
        """Deletes and removes a giveable role."""
        # Honestly this is the giveme delete command but modified to only delete from the DB
        if ',' in name:
            raise BadArgument('this command only works with single roles!')
        norm_name = self.normalize(name)
        valid_ids = set(role.id for role in ctx.guild.roles)
        roles = await GiveableRole.get_by(guild_id=ctx.guild.id)
        valid_roles = []
        for role_option in roles:
            if role_option.norm_name == norm_name and role_option.role_id in valid_ids:
                valid_roles.append(role_option)
        if len(valid_roles) == 0:
            raise BadArgument('that role does not exist or is not giveable!')
        elif len(valid_roles) > 1:
            raise BadArgument('multiple giveable roles with that name exist!')
        else:
            await GiveableRole.delete(guild_id=ctx.guild.id, norm_name=valid_roles[0].norm_name)
            await ctx.send('Role "{0}" deleted from list!'.format(name))

    delete.example_usage = """
    `{prefix}giveme removefromlist Java` - removes the role "Java" from the list of giveable roles but does not remove it from the server or members who have it 
    """

    @command()
    @bot_has_permissions(manage_roles=True, embed_links=True)
    @has_permissions(manage_roles=True)
    async def tempgive(self, ctx, member: discord.Member, length, *, role: discord.Role):
        """Temporarily gives a member a role for a set time. Not restricted to giveable roles."""
        if role > ctx.author.top_role:
            raise BadArgument('Cannot give roles higher than your top role!')

        ent = TempRoleTimerRecords(
            guild_id=member.guild.id,
            actor_id=ctx.author.id,
            target_id=member.id,
            target_role_id=role.id,
            removal_ts=self.calculate_epoch_time(length)
        )

        await ent.update_or_add()
        self.bot.loop.create_task(
            self.removal_timer(ent))
        await member.add_roles(role)
        e = discord.Embed(color=blurple)
        e.add_field(name='Success!', value='I gave {} to {}, for {}!'.format(role.mention, member.mention, length))
        e.set_footer(text='Triggered by ' + ctx.author.display_name)
        await ctx.send(embed=e)

    tempgive.example_usage = """
        `{prefix}tempgive cooldude#1234 Java 1h` - gives cooldude any role, giveable or not, named Java for one hour
        """

    @command()
    @bot_has_permissions(manage_roles=True, embed_links=True)
    @has_permissions(manage_roles=True)
    async def give(self, ctx, member: discord.Member, *, role: discord.Role):
        """Gives a member a role. Not restricted to giveable roles."""
        if role > ctx.author.top_role:
            raise BadArgument('Cannot give roles higher than your top role!')
        await member.add_roles(role)
        e = discord.Embed(color=blurple)
        e.add_field(name='Success!', value='I gave {} to {}!'.format(role, member))
        e.set_footer(text='Triggered by ' + ctx.author.display_name)
        await ctx.send(embed=e)

    give.example_usage = """
    `{prefix}give cooldude#1234 Java` - gives cooldude any role, giveable or not, named Java
    """

    @command()
    @bot_has_permissions(manage_roles=True, embed_links=True)
    @has_permissions(manage_roles=True)
    async def take(self, ctx, member: discord.Member, *, role: discord.Role):
        """Takes a role from a member. Not restricted to giveable roles."""
        if role > ctx.author.top_role:
            raise BadArgument('Cannot take roles higher than your top role!')
        await member.remove_roles(role)
        e = discord.Embed(color=blurple)
        e.add_field(name='Success!', value='I took {} from {}!'.format(role, member))
        e.set_footer(text='Triggered by ' + ctx.author.display_name)
        await ctx.send(embed=e)

    take.example_usage = """
    `{prefix}take cooldude#1234 Java` - takes any role named Java, giveable or not, from cooldude
    """


class GiveableRole(db.DatabaseTable):
    """Database object for maintaining a list of giveable roles."""
    __tablename__ = 'giveable_roles'
    __uniques__ = 'role_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint NOT NULL,
            role_id bigint PRIMARY KEY NOT NULL,
            name varchar NOT NULL,
            norm_name varchar NOT NULL
            )""")

    def __init__(self, guild_id, role_id, norm_name, name):
        super().__init__()
        self.guild_id = guild_id
        self.role_id = role_id
        self.name = name
        self.norm_name = norm_name

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = GiveableRole(guild_id=result.get("guild_id"), role_id=result.get("role_id"),
                               name=result.get("name"), norm_name=result.get("norm_name"))
            result_list.append(obj)
        return result_list

    @classmethod
    def from_role(cls, role):
        """Creates a GiveableRole record from a discord.Role."""
        return cls(role_id=role.id, name=role.name, norm_name=Roles.normalize(role.name), guild_id=role.guild.id)


class MissingRole(db.DatabaseTable):
    """Holds the roles of those who leave"""
    __tablename__ = 'missing_roles'
    __uniques__ = 'role_id, member_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint NOT NULL,
            member_id bigint NOT NULL,
            role_id bigint NOT NULL,
            role_name varchar NOT NULL,
            PRIMARY KEY (role_id, member_id)
            )""")

    def __init__(self, guild_id, member_id, role_id, role_name):
        super().__init__()
        self.guild_id = guild_id
        self.member_id = member_id
        self.role_id = role_id
        self.role_name = role_name

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = MissingRole(guild_id=result.get("guild_id"), role_id=result.get("role_id"),
                              member_id=result.get("member_id"), role_name=result.get("role_name"))
            result_list.append(obj)
        return result_list


class TempRoleTimerRecords(db.DatabaseTable):
    """TempRole Timer Records"""

    __tablename__ = 'temp_role_timers'
    __uniques__ = 'id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            id serial PRIMARY KEY NOT NULL,
            guild_id bigint NOT NULL,
            actor_id bigint NOT NULL,
            target_id bigint NOT NULL,
            target_role_id bigint NOT NULL,
            removal_ts bigint NOT NULL
            )""")

    def __init__(self, guild_id, actor_id, target_id, target_role_id, removal_ts, input_id=None):
        super().__init__()
        self.id = input_id
        self.guild_id = guild_id
        self.actor_id = actor_id
        self.target_id = target_id
        self.target_role_id = target_role_id
        self.removal_ts = removal_ts

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = TempRoleTimerRecords(guild_id=result.get("guild_id"), actor_id=result.get("actor_id"),
                                       target_id=result.get("target_id"),
                                       target_role_id=result.get("target_role_id"),
                                       removal_ts=result.get("removal_ts"),
                                       input_id=result.get('id'))
            result_list.append(obj)
        return result_list


def setup(bot):
    """Adds the roles cog to the main bot project."""
    bot.add_cog(Roles(bot))
