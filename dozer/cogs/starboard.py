"""Cog to post specific 'Hall of Fame' messages in a specific channel"""
import logging
import typing

import discord
from discord.ext.commands import guild_only, has_permissions

from ._utils import *
from .. import db

MAX_EMBED = 1024
DOZER_LOGGER = logging.getLogger('dozer')


async def is_cancelled(config, message, me, author=None):
    """Determine if the message has cancellation reacts"""
    if author is None:
        author = message.author

    for reaction in message.reactions:
        if str(reaction) != config.cancel_emoji:
            continue

        users = await reaction.users().flatten()
        if author in users or me in users:
            await message.add_reaction(config.cancel_emoji)
            return True

    return False


def make_starboard_embed(msg: discord.Message, reaction_count):
    """Makes a starboard embed."""
    e = discord.Embed(color=msg.author.color, title="New Starred Message")
    e.set_author(name=msg.author.display_name, icon_url=msg.author.avatar_url)

    view_link = f" [[view]]({msg.jump_url})"
    if not len(msg.content):
        e.add_field(name="Link:", value=view_link)
    elif len(msg.content) < (MAX_EMBED - len(view_link)):
        e.add_field(name="Content:", value=msg.content + view_link)
    elif len(msg.content) < MAX_EMBED:
        e.add_field(name="Content:", value=msg.content)
        e.add_field(name="Link:", value=view_link)
    elif len(msg.content) < ((2*MAX_EMBED) - len(view_link)):
        e.add_field(name="Content:", value=msg.content[0:MAX_EMBED], inline=False)
        e.add_field(name="More:", value=msg.content[MAX_EMBED:2000] + view_link, inline=False)
    else:
        e.add_field(name="Content:", value=msg.content[0:MAX_EMBED], inline=False)
        e.add_field(name="More:", value=msg.content[MAX_EMBED:2000], inline=False)
        e.add_field(name="Link:", value=view_link)

    if len(msg.attachments) > 1:
        e.add_field(name="Attachments:", value="\n".join([a.url for a in msg.attachments[1:]]))
    if len(msg.attachments) == 1:
        if msg.attachments[0].width is not None:
            e.set_image(url=msg.attachments[0].url)
        else:
            e.add_field(name="Attachment:", value=f"[{msg.attachments[0].filename}]({msg.attachments[0].url})")

    e.set_footer(text=f"{reaction_count} reactions")
    e.timestamp = msg.created_at
    return e


class Starboard(Cog):
    """Cog to post specific 'Hall of Fame' messages in a specific channel"""

    def __init__(self, bot):
        super().__init__(bot)
        self.config_cache = {}

    def make_config_embed(self, ctx, title, config):
        """Makes a config embed."""
        e = discord.Embed(title=title, color=discord.Color.gold())
        e.add_field(name="Starboard Channel", value=self.bot.get_channel(config.channel_id).mention)
        e.add_field(name="Starboard Emoji", value=config.star_emoji)
        e.add_field(name="Cancel Emoji", value=config.cancel_emoji)
        e.add_field(name="Threshold", value=config.threshold)
        e.set_footer(text=f"For more information, try {ctx.prefix}help starboard")
        return e

    async def send_to_starboard(self, config, message, reaction_count):
        """GIven a message which may or may not exist, send it to the starboard"""
        starboard_channel = message.guild.get_channel(config.channel_id)
        if starboard_channel is None:
            return

        db_msgs = await StarboardMessage.get_by(message_id=message.id)
        if len(db_msgs) == 0:
            sent_msg = await starboard_channel.send(embed=make_starboard_embed(message, reaction_count))
            db_msg = StarboardMessage(message.id, message.channel.id, sent_msg.id, message.author.id)
            await db_msg.update_or_add()
            await message.add_reaction(config.star_emoji)
        else:
            try:
                sent_msg = await self.bot.get_channel(config.channel_id).fetch_message(db_msgs[0].starboard_message_id)
            except discord.errors.NotFound:
                # Uh oh! Starboard message was deleted. Let's try and delete it
                DOZER_LOGGER.warning(f"Cannot find Starboard Message {db_msgs[0].starboard_message_id} to update")
                fake_msg = discord.Object(db_msgs[0].starboard_message_id)
                await self.remove_from_starboard(config, fake_msg, True)
                return
            await sent_msg.edit(embed=make_starboard_embed(message, reaction_count-1))

    async def remove_from_starboard(self, config, starboard_message, cancel=False):
        """Given a starboard message or snowflake, remove that message and remove it from the DB"""
        db_msgs = await StarboardMessage.get_by(starboard_message_id=starboard_message.id)
        if len(db_msgs):
            if hasattr(starboard_message, 'delete'):
                await starboard_message.delete()
            if cancel:
                orig_msg = await self.bot.get_channel(db_msgs[0].channel_id).fetch_message(db_msgs[0].message_id)
                await orig_msg.add_reaction(config.cancel_emoji)
            await StarboardMessage.delete(message_id=db_msgs[0].message_id)

    async def starboard_check(self, reaction, member):
        """Provides all logic for checking and updating the Starboard"""
        msg = reaction.message
        if not msg.guild:
            return

        if msg.guild.id in self.config_cache:
            config = self.config_cache[msg.guild.id]
        else:
            config_lst = await StarboardConfig.get_by(guild_id=msg.guild.id)
            if len(config_lst) == 1:
                self.config_cache[msg.guild] = config_lst[0]
                config = config_lst[0]
            else:
                return

        # Starboard check
        if str(reaction) == config.star_emoji and reaction.count >= config.threshold and \
                member != msg.guild.me and not await is_cancelled(config, msg, msg.guild.me):
            DOZER_LOGGER.debug("Starboard threshold reached, sending to starboard")
            await self.send_to_starboard(config, msg, reaction.count)
            return

        # check if it's gone under the limit
        if str(reaction) == config.star_emoji and reaction.count < config.threshold:
            db_msgs = await StarboardMessage.get_by(message_id=msg.id)
            if len(db_msgs):
                DOZER_LOGGER.debug("Under starboard threshold, removing starboard")
                starboard_msg = await self.bot.get_channel(config.channel_id).\
                    fetch_message(db_msgs[0].starboard_message_id)
                await self.remove_from_starboard(config, starboard_msg)
                return

        # check if it's been cancelled in the starboard channel
        if str(reaction) == config.cancel_emoji and msg.channel.id == config.channel_id:
            db_msgs = await StarboardMessage.get_by(starboard_message_id=msg.id)
            if len(db_msgs) and member.id == db_msgs[0].author_id:
                DOZER_LOGGER.debug("Message cancelled in starboard channel, cancelling")
                await self.remove_from_starboard(config, msg, True)
                return

        # check if it's been cancelled on the original message
        if str(reaction) == config.cancel_emoji:
            db_msgs = await StarboardMessage.get_by(message_id=msg.id)
            if len(db_msgs) and member.id == db_msgs[0].author_id:
                DOZER_LOGGER.debug("Message cancelled in original channel, cancelling")
                starboard_msg = await self.bot.get_channel(config.channel_id). \
                    fetch_message(db_msgs[0].starboard_message_id)
                await self.remove_from_starboard(config, starboard_msg, True)
                return

    @Cog.listener()
    async def on_reaction_add(self, reaction, user):
        """Pass the reaction add event onto our handler"""
        await self.starboard_check(reaction, user)

    @Cog.listener()
    async def on_reaction_remove(self, reaction, user):
        """Pass the reaction remove event onto our handler"""
        await self.starboard_check(reaction, user)

    @guild_only()
    @group(invoke_without_command=True, aliases=['hof'])
    async def starboard(self, ctx):
        """Show the current server's starboard configuration.
         A starboard (or a hall of fame) is a channel the bot will repost messages in if they receive a certain number\
         of configured reactions.

         To configure a starboard, use the `starboard config` subcommand.
         """
        config = await StarboardConfig.get_by(guild_id=ctx.guild.id)

        if config:
            await ctx.send(embed=self.make_config_embed(ctx, f"Starboard configuration for {ctx.guild}", config[0]))
        else:
            await ctx.send(f"This server does not have a starboard configured! See `{ctx.prefix}help starboard` for "
                           f"more information.")

    starboard.example_usage = """
    `{prefix}starboard` - Get the current starboard settings for this server
    """

    @has_permissions(manage_guild=True, manage_channels=True)
    @bot_has_permissions(add_reactions=True, embed_links=True)
    @starboard.command()
    async def config(self, ctx, channel: discord.TextChannel, star_emoji: typing.Union[discord.Emoji, str],
                     threshold: int,
                     cancel_emoji: typing.Union[discord.Emoji, str] = None):
        """Modify the settings for this server's starboard"""
        for emoji in [emoji for emoji in [star_emoji, cancel_emoji] if emoji is not None]:
            try:
                # try adding it to make sure it's a real emoji. This covers both custom emoijs & unicode emojis
                await ctx.message.add_reaction(emoji)
                await ctx.message.remove_reaction(emoji, ctx.guild.me)
            except discord.HTTPException:
                await ctx.send(f"{ctx.author.mention}, bad argument: '{emoji}' is not an emoji, or isn't from a server "
                               f"{ctx.me.name} is in.")
                return

        config = StarboardConfig(guild_id=ctx.guild.id, channel_id=channel.id, star_emoji=str(star_emoji),
                                 threshold=threshold, cancel_emoji=str(cancel_emoji))
        await config.update_or_add()
        self.config_cache[ctx.guild] = config

        await ctx.send(embed=self.make_config_embed(ctx, "Update Starboard config", config))

    config.example_usage = """
    `{prefix}starboard config #hall-of-fame 🌟 5` - Set the bot to repost messages that have 5 star reactions to `#hall-of-fame
    `{prefix}starboard config #hall-of-fame 🌟 5 ❌` - Same as above, but with a extra X cancel emoji 
    """

    @has_permissions(manage_guild=True, manage_channels=True)
    @starboard.command()
    async def disable(self, ctx):
        """Turn off the starboard if it is enabled"""
        config = await StarboardConfig.get_by(guild_id=ctx.guild.id)
        if not config:
            await ctx.send("There is not Starboard set up for this server.")
            return

        await StarboardConfig.delete(guild_id=ctx.guild.it)
        try:
            del self.config_cache[ctx.guild]
        except KeyError:
            pass

        await ctx.send("Starboard disabled for this server.")

    disable.example_usage = """
    `{prefix}starboard disable` - disables the starboard for the current server
    """

    @has_permissions(manage_messages=True)
    @starboard.command()
    async def add(self, ctx, message_id, channel: discord.TextChannel = None):
        """Add a message to the starboard manually"""
        config = await StarboardConfig.get_by(guild_id=ctx.guild.id)
        if len(config) == 0:
            await ctx.send(f"There is not a Starboard configured for this server. Set one up with "
                           f"`{ctx.bot.config}starboard config`")
            return
        if channel is None:
            channel = ctx.channel

        try:
            msg = await channel.fetch_message(message_id)
            for reaction in msg.reactions:
                if str(reaction) != config[0].star_emoji:
                    await self.send_to_starboard(config[0], msg, reaction.count)
                    break
        except discord.NotFound:
            await ctx.send(f"Message {message_id} not found in {channel.mention}")

        await ctx.send(f"Successfully posted message {message_id} to the starboard!")

    add.example_usage = """
    `{prefix}starboard add 1285719825125 #channel` - add message with id `1285719825125` in `#channel` to the starboard 
    manually.
    """

def setup(bot):
    """Add this cog to the bot"""
    bot.add_cog(Starboard(bot))


class StarboardConfig(db.DatabaseTable):
    """Each starboard-related setting"""
    __tablename__ = 'starboard_settings'
    __uniques__ = 'guild_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY NOT NULL,
            channel_id bigint NOT NULL,
            star_emoji varchar NOT NULL,
            cancel_emoji varchar,
            threshold bigint NOT NULL
            )""")

    def __init__(self, guild_id, channel_id, star_emoji, threshold, cancel_emoji=None):
        super().__init__()
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.star_emoji = star_emoji
        self.cancel_emoji = cancel_emoji
        self.threshold = threshold

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = StarboardConfig(guild_id=result.get("guild_id"), channel_id=result.get("channel_id"),
                                  star_emoji=result.get('star_emoji'), cancel_emoji=result.get('cancel_emoji'),
                                  threshold=result.get('threshold'))
            result_list.append(obj)
        return result_list


class StarboardMessage(db.DatabaseTable):
    """Each starboard-related setting"""
    __tablename__ = 'starboard_message'
    __uniques__ = 'message_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            message_id bigint PRIMARY KEY NOT NULL,
            channel_id bigint NOT NULL,
            starboard_message_id bigint NOT NULL,
            author_id bigint NOT NULL
            )""")

    def __init__(self, message_id, channel_id, starboard_message_id, author_id):
        super().__init__()
        self.message_id = message_id
        self.channel_id = channel_id
        self.starboard_message_id = starboard_message_id
        self.author_id = author_id

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = StarboardMessage(message_id=result.get("message_id"),
                                   channel_id=result.get("channel_id"),
                                   starboard_message_id=result.get("starboard_message_id"),
                                   author_id=result.get('author_id'))
            result_list.append(obj)
        return result_list
