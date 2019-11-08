"""General, basic commands that are common for Discord bots"""

import inspect
import discord
from discord.ext.commands import BadArgument, cooldown, BucketType, Group, has_permissions

from ._utils import *
from .. import db


class General(Cog):
    """General commands common to all Discord bots."""

    @command()
    async def ping(self, ctx):
        """Check the bot is online, and calculate its response time."""
        if ctx.guild is None:
            location = 'DMs'
        else:
            location = 'the **%s** server' % ctx.guild.name
        response = await ctx.send('Pong! We\'re in %s.' % location)
        delay = response.created_at - ctx.message.created_at
        await response.edit(
            content=response.content + '\nTook %d ms to respond.' % (delay.seconds * 1000 + delay.microseconds // 1000))

    ping.example_usage = """
    `{prefix}ping` - Calculate and display the bot's response time
    """

    @cooldown(1, 10, BucketType.channel)
    @command(name='help', aliases=['about'])
    @bot_has_permissions(add_reactions=True, embed_links=True,
                         read_message_history=True)  # Message history is for internals of paginate()
    async def base_help(self, ctx, *target):
        """Show this message."""
        if not target:  # No commands - general help
            await self._help_all(ctx)
        elif len(target) == 1:  # Cog or command
            target_name = target[0]
            if target_name in ctx.bot.cogs:
                await self._help_cog(ctx, ctx.bot.cogs[target_name])
            else:
                command = ctx.bot.get_command(target_name)
                if command is None:
                    raise BadArgument('that command/cog does not exist!')
                else:
                    await self._help_command(ctx, command)
        else:  # Command with subcommand
            command = ctx.bot.get_command(' '.join(target))
            if command is None:
                raise BadArgument('that command does not exist!')
            else:
                await self._help_command(ctx, command)

    base_help.example_usage = """
    `{prefix}help` - General help message
    `{prefix}help help` - Help about the help command
    `{prefix}help General` - Help about the General category
    """

    async def _help_all(self, ctx):
        """Gets the help message for all commands."""
        info = discord.Embed(title='Dozer: Info', description='A guild management bot for FIRST Discord servers',
                             color=discord.Color.blue())
        info.set_thumbnail(url=self.bot.user.avatar_url)
        info.add_field(name='About',
                       value="Dozer: A collaborative bot for FIRST Discord servers, developed by the FRC Discord Server Development Team")
        info.add_field(name='About `{}{}`'.format(ctx.prefix, ctx.invoked_with), value=inspect.cleandoc("""
        This command can show info for all commands, a specific command, or a category of commands.
        Use `{0}{1} {1}` for more information.
        """.format(ctx.prefix, ctx.invoked_with)), inline=False)
        info.add_field(name='Support',
                       value="Join our development server at https://discord.gg/bB8tcQ8 for support, to help with development, or if "
                             "you have any questions or comments!")
        info.add_field(name="Open Source",
                       value="Dozer is open source! Feel free to view and contribute to our Python code "
                             "[on Github](https://github.com/FRCDiscord/Dozer)")
        info.set_footer(text='Dozer Help | all commands | Info page')
        await self._show_help(ctx, info, 'Dozer: Commands', '', 'all commands', ctx.bot.commands)

    async def _help_command(self, ctx, command):
        """Gets the help message for one command."""
        info = discord.Embed(title='Command: {}{}'.format(ctx.prefix, command.signature), description=command.help or (
            None if command.example_usage else 'No information provided.'), color=discord.Color.blue())
        usage = command.example_usage
        if usage is not None:
            info.add_field(name='Usage', value=usage.format(prefix=ctx.prefix, name=ctx.invoked_with), inline=False)
        info.set_footer(text='Dozer Help | {!r} command | Info'.format(command.qualified_name))
        await self._show_help(ctx, info, 'Subcommands: {prefix}{signature}', '', '{command.qualified_name!r} command',
                              command.commands if isinstance(command, Group) else set(), command=command, signature=command.signature)

    async def _help_cog(self, ctx, cog):
        """Gets the help message for one cog."""
        await self._show_help(ctx, None, 'Category: {cog_name}', inspect.cleandoc(cog.__doc__ or ''),
                              '{cog_name!r} category',
                              (command for command in ctx.bot.commands if command.instance is cog),
                              cog_name=type(cog).__name__)

    async def _show_help(self, ctx, start_page, title, description, footer, commands, **format_args):
        """Creates and sends a template help message, with arguments filled in."""
        format_args['prefix'] = ctx.prefix
        footer = 'Dozer Help | {} | Page {}'.format(footer,
                                                    '{page_num} of {len_pages}')
        # Page info is inserted as a parameter so page_num and len_pages aren't evaluated now
        if commands:
            command_chunks = list(chunk(sorted(commands, key=lambda cmd: cmd.name), 4))
            format_args['len_pages'] = len(command_chunks)
            pages = []
            for page_num, page_commands in enumerate(command_chunks):
                format_args['page_num'] = page_num + 1
                page = discord.Embed(title=title.format(**format_args), description=description.format(**format_args), color=discord.Color.blue())
                for command in page_commands:
                    if command.short_doc:
                        embed_value = command.short_doc
                    elif command.example_usage:  # Usage provided - show the user the command to see it
                        embed_value = 'Use `{0.prefix}{0.invoked_with} {1.qualified_name}` for more information.'.format(
                            ctx, command)
                    else:
                        embed_value = 'No information provided.'
                    page.add_field(name=ctx.prefix + command.signature, value=embed_value, inline=False)
                page.set_footer(text=footer.format(**format_args))
                pages.append(page)

            if start_page is not None:
                pages.append({'info': start_page})

            if len(pages) == 1:
                await ctx.send(embed=pages[0])
            elif start_page is not None:
                info_emoji = '\N{INFORMATION SOURCE}'
                p = Paginator(ctx, (info_emoji, ...), pages, start='info',
                              auto_remove=ctx.channel.permissions_for(ctx.me))
                async for reaction in p:
                    if reaction == info_emoji:
                        p.go_to_page('info')
            else:
                await paginate(ctx, pages, auto_remove=ctx.channel.permissions_for(ctx.me))
        elif start_page:  # No commands - command without subcommands or empty cog - but a usable info page
            await ctx.send(embed=start_page)
        else:  # No commands, and no info page
            format_args['len_pages'] = 1
            format_args['page_num'] = 1
            embed = discord.Embed(title=title.format(**format_args), description=description.format(**format_args), color=discord.Color.blue())
            embed.set_footer(text=footer.format(**format_args))
            await ctx.send(embed=embed)

    @has_permissions(change_nickname=True)
    @command()
    async def nick(self, ctx, *, nicktochangeto):
        """Allows a member to change their nickname."""
        await discord.Member.edit(ctx.author, nick=nicktochangeto[:32])
        await ctx.send("Nick successfully changed to " + nicktochangeto[:32])
        if len(nicktochangeto) > 32:
            await ctx.send("Warning: truncated nickname to 32 characters")

    @command()
    async def invite(self, ctx):
        """
        Display the bot's invite link.
        The generated link gives all permissions the bot requires. If permissions are removed, some commands will be unusable.
        """
        perms = 0
        for cmd in ctx.bot.walk_commands():
            perms |= cmd.required_permissions.value
        await ctx.send('<{}>'.format(discord.utils.oauth_url(ctx.me.id, discord.Permissions(perms))))

    @has_permissions(create_instant_invite=True)
    @bot_has_permissions(create_instant_invite=True)
    @command()
    async def invites(self, ctx, num, hours=24):
        """
        Generates a set number of single use invites.
        """

        settings = await WelcomeChannel.get_by_channel(ctx.guild.id)
        if settings is None:
            await ctx.send(
                "There is no welcome channel set. Please set one using `{0}welcomeconfig channel` and try again.".format(
                    ctx.prefix))
            return
        else:
            invitechannel = ctx.bot.get_channel(settings[0].channel_id)
            if invitechannel is None:
                await ctx.send(
                    "There was an issue getting your welcome channel. Please set it again using `{0} welcomeconfig channel`.".format(
                        ctx.prefix))
                return
            text = ""
            for i in range(int(num)):
                invite = await invitechannel.create_invite(max_age=hours * 3600, max_uses=1, unique=True,
                                                           reason="Autogenerated by {}".format(ctx.author))
                text += "Invite {0}: <{1}>\n".format(i + 1, invite.url)
            await ctx.send(text)

    invites.example_usage = """
    `{prefix}invtes 5` - Generates 5 single use invites.
    `{prefix}invites 2 12` Generates 2 single use invites that last for 12 hours.
    """

    @command()
    @has_permissions(administrator=True)
    async def welcomeconfig(self, ctx, *, welcome_channel: discord.TextChannel):
        """
        Sets the new member channel for this guild.
        """
        if welcome_channel.guild != ctx.guild:
            await ctx.send("That channel is not in this guild.")
            return
        settings = WelcomeChannel(ctx.guild.id, welcome_channel.id)
        await settings.update_or_add()
        await ctx.send("Welcome channel set to {}".format(welcome_channel.mention))

    welcomeconfig.example_usage = """
    `{prefix}welcomeconfig #new-members` - Sets the invite channel to #new-members.
    """


def setup(bot):
    """Adds the general cog to the bot"""
    bot.remove_command('help')
    bot.add_cog(General(bot))


class WelcomeChannel(db.DatabaseTable):
    __tablename__ = 'welcome_channel'
    __uniques__ = 'guild_id'
    @classmethod
    async def initial_create(cls):
        """Create the table in the database with just the ID field. Overwrite this field in your subclasses with your
        full schema. Make sure your DB rows have the exact same name as the python variable names."""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY,
            channel_id bigint null
            )""")

    # @classmethod
    # async def initial_migrate(cls):
    #     async with db.Pool.acquire() as conn:
    #         await conn.execute("""ALTER TABLE welcome_channel RENAME id TO guild_id""")

    def __init__(self, guild_id, channel_id):
        super().__init__()
        self.guild_id = guild_id
        self.channel_id = channel_id

    async def get_by_attribute(self, obj_id, column_name):
        """Gets a list of all objects with a given attribute"""
        async with db.Pool.acquire() as conn:  # Use transaction here?
            stmt = await conn.fetch(f"""SELECT * FROM {self.__tablename__} WHERE {column_name} = {obj_id}""")
            results = await stmt.fetch()
            list = []
            for result in results:
                obj = WelcomeChannel(guild_id=result.get("guild_id"), channel_id=result.get("channel_id"))
                # for var in obj.__dict__:
                #     setattr(obj, var, result.get(var))
                list.append(obj)
            return list

