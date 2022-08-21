"""General, basic commands that are common for Discord bots"""
import inspect

import discord
from discord.ext.commands import BadArgument, cooldown, BucketType, Group, has_permissions, NotOwner, guild_only
from discord.utils import escape_markdown

from dozer.context import DozerContext
from ._utils import *
from ..utils import oauth_url

blurple = discord.Color.blurple()


class General(Cog):
    """General commands common to all Discord bots."""

    @command()
    async def ping(self, ctx: DozerContext):
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
    async def base_help(self, ctx: DozerContext, *, target=None):
        """Show this message."""
        try:
            target = target.split(" ")
        except AttributeError:  # No commands - general help
            await self._help_all(ctx)
        if target is None:
            pass
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

    async def _help_all(self, ctx: DozerContext):
        """Gets the help message for all commands."""
        info = discord.Embed(title='Dozer: Info', description='A guild management bot for FIRST Discord servers',
                             color=discord.Color.blue())
        info.set_thumbnail(url=self.bot.user.avatar)
        info.add_field(name='About',
                       value="Dozer: A collaborative bot for FIRST Discord servers, developed by the FRC Discord Server Development Team")
        info.add_field(name='About `{}{}`'.format(ctx.prefix, ctx.invoked_with), value=inspect.cleandoc("""
        This command can show info for all commands, a specific command, or a category of commands.
        Use `{0}{1} {1}` for more information.
        """.format(ctx.prefix, ctx.invoked_with)), inline=False)

        info.add_field(name="Open Source",
                       value="Dozer is open source! Feel free to view and contribute to our Python code "
                             "[on Github](https://github.com/FRCDiscord/Dozer)", inline=False)
        info.add_field(name='Support',
                       value="If you have any questions or comments you can join our [support server](https://discord.gg/bB8tcQ8) ")
        info.add_field(name="Privacy",
                       value="We are fully committed to protecting your privacy. "
                             "You can view our privacy policy [here](https://github.com/FRCDiscord/Dozer/blob/master/privacy.md)")
        info.set_footer(text='Dozer Help | all commands | Info page')
        await self._show_help(ctx, info, 'Dozer: Commands', '', 'all commands', ctx.bot.commands)

    async def _help_command(self, ctx: DozerContext, command):
        """Gets the help message for one command."""
        info = discord.Embed(title='Command: {}{} {}'.format(ctx.prefix, command.qualified_name, command.signature),
                             description=command.help or (
                                 None if command.example_usage else 'No information provided.'),
                             color=discord.Color.blue())
        usage = command.example_usage
        if usage:
            info.add_field(name='Usage', value=usage.format(prefix=ctx.prefix, name=ctx.invoked_with), inline=False)
        info.set_footer(text='Dozer Help | {!r} command | Info'.format(command.qualified_name))
        await self._show_help(ctx, info, 'Subcommands: {prefix}{name} {signature}', '', '{name!r} command',
                              command.commands if isinstance(command, Group) else set(),
                              name=command.qualified_name, signature=command.signature)

    async def _help_cog(self, ctx: DozerContext, cog):
        """Gets the help message for one cog."""
        await self._show_help(ctx, None, 'Category: {cog_name}', inspect.cleandoc(cog.__doc__ or ''),
                              '{cog_name!r} category',
                              (command for command in ctx.bot.commands if command.cog is cog),
                              cog_name=type(cog).__name__)

    async def _show_help(self, ctx: DozerContext, start_page: discord.Embed, title: str, description: str,
                         footer: str, commands, **format_args):
        """Creates and sends a template help message, with arguments filled in."""
        format_args['prefix'] = ctx.prefix
        footer = 'Dozer Help | {} | Page {}'.format(footer, '{page_num} of {len_pages}')
        # Page info is inserted as a parameter so page_num and len_pages aren't evaluated now

        if commands:
            filtered_commands = []
            for sort_command in commands:
                try:
                    sort_command.cog.cog_check(ctx)
                    filtered_commands.append(sort_command)
                except NotOwner:
                    continue
            command_chunks = list(chunk(sorted(filtered_commands, key=lambda cmd: cmd.name), 4))
            format_args['len_pages'] = len(command_chunks)
            pages = []
            for page_num, page_commands in enumerate(command_chunks):
                format_args['page_num'] = page_num + 1
                page = discord.Embed(title=title.format(**format_args), description=description.format(**format_args),
                                     color=discord.Color.blue())
                for command in page_commands:
                    if command.short_doc:
                        embed_value = command.short_doc
                    elif command.example_usage:  # Usage provided - show the user the command to see it
                        embed_value = 'Use `{0.prefix}{0.invoked_with} {1.qualified_name}` for more information.'.format(
                            ctx, command)
                    else:
                        embed_value = 'No information provided.'
                    page.add_field(name='{}{} {}'.format(ctx.prefix, command.qualified_name, command.signature),
                                   value=embed_value, inline=False)
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
            embed = discord.Embed(title=title.format(**format_args), description=description.format(**format_args),
                                  color=discord.Color.blue())
            embed.set_footer(text=footer.format(**format_args))
            await ctx.send(embed=embed)

    @has_permissions(change_nickname=True)
    @command()
    async def nick(self, ctx: DozerContext, *, nicktochangeto: str):
        """Allows a member to change their nickname."""
        await discord.Member.edit(ctx.author, nick=nicktochangeto[:32])
        await ctx.send("Nick successfully changed to " + nicktochangeto[:32])
        if len(nicktochangeto) > 32:
            await ctx.send("Warning: truncated nickname to 32 characters")

    @command()
    async def invite(self, ctx: DozerContext):
        """
        Display the bot's invite link.
        The generated link gives all permissions the bot requires. If permissions are removed, some commands will be unusable.
        """
        bot_info = await self.bot.application_info()
        if not bot_info.bot_public or self.bot.config['invite_override'] != "":
            await ctx.send(self.bot.config['invite_override'] or "The bot is not able to be publicly invited. Please "
                                                                 "contact the bot developer. If you are the bot "
                                                                 "developer, please check the bot console. ")
            return
        perms = 0
        for cmd in ctx.bot.walk_commands():
            perms |= cmd.required_permissions.value
        await ctx.send('<{}>'.format(oauth_url(ctx.me.id, discord.Permissions(perms))))

    @command(aliases=["setprefix"])
    @guild_only()
    @has_permissions(manage_guild=True)
    async def configprefix(self, ctx: DozerContext, prefix: str):
        """Update a servers dynamic prefix"""
        new_prefix = DynamicPrefixEntry(
            guild_id=int(ctx.guild.id),
            prefix=prefix
        )
        await new_prefix.update_or_add()
        await self.bot.dynamic_prefix.refresh()
        e = discord.Embed(color=blurple)
        e.add_field(name='Success!', value=f"`{ctx.guild}`'s prefix has set to `{prefix}`!")
        e.set_footer(text='Triggered by ' + escape_markdown(ctx.author.display_name))
        await ctx.send(embed=e)


async def setup(bot):
    """Adds the general cog to the bot"""
    bot.remove_command('help')
    await bot.add_cog(General(bot))
