"""Cog to post specific 'Hall of Fame' messages in a specific channel"""
import asyncio
import logging
from typing import List, Set, Optional
from typing import TYPE_CHECKING

import discord
from discord.ext.commands import guild_only, has_permissions
from discord.utils import escape_markdown

from dozer.context import DozerContext
from ._utils import *
from .. import db

if TYPE_CHECKING:
    from dozer import Dozer

MAX_EMBED: int = 1024
LOCK_TIME: float = .1
FORCE_TRY_TIME: int = 1
DOZER_LOGGER = logging.getLogger('dozer')
VIDEO_FORMATS: List[str] = ['.mp4', '.mov', 'webm']


async def is_cancelled(emoji: str, message: discord.Message, me: discord.Member, author: discord.Member = None) -> bool:
    """Determine if the message has cancellation reacts"""
    if author is None:
        author = message.author

    for reaction in message.reactions:
        if str(reaction) != emoji:
            continue

        users = [user async for user in reaction.users()]
        if author in users or me in users:
            return True
        return False

    return False


def make_starboard_embed(msg: discord.Message, reaction_count: int) -> discord.Embed:
    """Makes a starboard embed."""
    e: discord.Embed = discord.Embed(color=msg.author.color, title=f"New Starred Message in #{msg.channel.name}",
                                     description=msg.content, url=msg.jump_url)
    e.set_author(name=escape_markdown(msg.author.display_name), icon_url=msg.author.avatar)

    view_link: str = f" [[view]]({msg.jump_url})"
    e.add_field(name="Link:", value=view_link)

    if len(msg.attachments) > 1:
        e.add_field(name="Attachments:", value="\n".join([f"[{a.filename}]({a.url})" for a in msg.attachments]))
    elif len(msg.attachments) == 1:
        if msg.attachments[0].width is not None and msg.attachments[0].filename[-4:] not in VIDEO_FORMATS and not \
                msg.attachments[0].is_spoiler():
            e.set_image(url=msg.attachments[0].url)
        else:
            e.add_field(name="Attachment:", value=f"[{msg.attachments[0].filename}]({msg.attachments[0].url})")

    e.set_footer(text=f"{reaction_count} reaction{'s' if reaction_count != 1 else ''}")
    e.timestamp = msg.created_at
    return e


class Starboard(Cog):
    """Cog to post specific 'Hall of Fame' messages in a specific channel"""

    def __init__(self, bot: "Dozer"):
        super().__init__(bot)
        self.config_cache: db.ConfigCache = db.ConfigCache(StarboardConfig)
        self.locked_messages: Set = set()

    def make_config_embed(self, ctx: DozerContext, title, config) -> discord.Embed:
        """Makes a config embed."""
        channel: discord.TextChannel = self.bot.get_channel(config.channel_id)
        if channel is None:
            return discord.Embed(title="Starboard channel no longer exists!",
                                 description="Please reconfigure the starboard to fix this.",
                                 color=discord.colour.Color.red())

        e: discord.Embed = discord.Embed(title=title, color=discord.Color.gold())
        e.add_field(name="Starboard Channel", value=channel.mention)
        e.add_field(name="Starboard Emoji", value=config.star_emoji)
        e.add_field(name="Cancel Emoji", value=config.cancel_emoji)
        e.add_field(name="Threshold", value=config.threshold)
        e.set_footer(text=f"For more information, try {ctx.prefix}help starboard")
        return e

    async def send_to_starboard(self, config: "StarboardConfig", message: discord.Message, reaction_count: int, add_react: bool = True):
        """Given a message which may or may not exist, send it to the starboard"""
        starboard_channel = message.guild.get_channel(config.channel_id)
        if starboard_channel is None:
            return

        # check if the message we're trying to HoF is a hof message
        starboard_check = await StarboardMessage.get_by(starboard_message_id=message.id)
        if len(starboard_check):
            DOZER_LOGGER.info("Attempt to star starboard message, skipping")
            return

        db_msgs = await StarboardMessage.get_by(message_id=message.id)
        if len(db_msgs) == 0:
            sent_msg = await starboard_channel.send(embed=make_starboard_embed(message, reaction_count))
            db_msg = StarboardMessage(message.id, message.channel.id, sent_msg.id, message.author.id)
            await db_msg.update_or_add()
            if add_react:
                await message.add_reaction(config.star_emoji)
        else:
            try:
                sent_msg: discord.Message = await self.bot.get_channel(config.channel_id).fetch_message(db_msgs[0].starboard_message_id)
            except discord.errors.NotFound:
                # Uh oh! Starboard message was deleted. Let's try and delete it
                DOZER_LOGGER.warning(f"Cannot find Starboard Message {db_msgs[0].starboard_message_id} to update")
                fake_msg = discord.Object(db_msgs[0].starboard_message_id)
                await self.remove_from_starboard(config, fake_msg, True)
                return
            await sent_msg.edit(embed=make_starboard_embed(message, reaction_count - 1))

    async def remove_from_starboard(self, config, starboard_message: discord.Message, cancel: bool = False):
        """Given a starboard message or snowflake, remove that message and remove it from the DB"""
        db_msgs: List[StarboardMessage] = await StarboardMessage.get_by(starboard_message_id=starboard_message.id)
        if len(db_msgs):
            if hasattr(starboard_message, 'delete'):
                await starboard_message.delete()
            if cancel:
                try:
                    orig_msg: discord.Message = await self.bot.get_channel(db_msgs[0].channel_id).fetch_message(db_msgs[0].message_id)
                    await orig_msg.add_reaction(config.cancel_emoji)
                except discord.NotFound:
                    pass
            await StarboardMessage.delete(message_id=db_msgs[0].message_id)

    async def starboard_check(self, reaction: discord.Reaction, member: discord.Member):
        """Provides all logic for checking and updating the Starboard"""
        msg: discord.Message = reaction.message
        if not msg.guild:
            return

        config: StarboardConfig = await self.config_cache.query_one(guild_id=msg.guild.id)
        if config is None:
            return

        time_waiting = 0
        while msg in self.locked_messages and time_waiting < FORCE_TRY_TIME:
            await asyncio.sleep(LOCK_TIME)
            time_waiting += LOCK_TIME
        self.locked_messages.add(msg)

        self_react = 0
        if await is_cancelled(config.star_emoji, msg, msg.guild.me, msg.guild.me):
            self_react = 1

        # Starboard check
        if str(reaction) == config.star_emoji and (reaction.count - self_react) >= config.threshold and \
                member != msg.guild.me and not await is_cancelled(config.cancel_emoji, msg, msg.guild.me):
            DOZER_LOGGER.debug(f"Starboard threshold reached on message {reaction.message.id} in "
                               f"{reaction.message.guild.name} from user {member.id}, sending to starboard")
            await self.send_to_starboard(config, msg, reaction.count)

        # check if it's gone under the limit
        elif str(reaction) == config.star_emoji and (reaction.count - self_react) < config.threshold:
            db_msgs = await StarboardMessage.get_by(message_id=msg.id)
            if len(db_msgs):
                DOZER_LOGGER.debug("Under starboard threshold, removing starboard")
                try:
                    starboard_msg = await self.bot.get_channel(config.channel_id). \
                        fetch_message(db_msgs[0].starboard_message_id)
                except discord.NotFound:
                    DOZER_LOGGER.warning(f"Cannot find Starboard Message {db_msgs[0].starboard_message_id} to remove")
                    starboard_msg = discord.Object(db_msgs[0].starboard_message_id)
                await self.remove_from_starboard(config, starboard_msg)

        # check if it's been cancelled in the starboard channel
        elif str(reaction) == config.cancel_emoji and msg.channel.id == config.channel_id:
            db_msgs = await StarboardMessage.get_by(starboard_message_id=msg.id)
            if len(db_msgs) and member.id == db_msgs[0].author_id:
                DOZER_LOGGER.debug("Message cancelled in starboard channel, cancelling")
                await self.remove_from_starboard(config, msg, True)

        # check if it's been cancelled on the original message
        elif str(reaction) == config.cancel_emoji:
            db_msgs = await StarboardMessage.get_by(message_id=msg.id)
            if len(db_msgs) and member.id == db_msgs[0].author_id:
                DOZER_LOGGER.debug("Message cancelled in original channel, cancelling")
                try:
                    starboard_msg = await self.bot.get_channel(config.channel_id). \
                        fetch_message(db_msgs[0].starboard_message_id)
                except discord.NotFound:
                    DOZER_LOGGER.warning(f"Cannot find Starboard Message {db_msgs[0].starboard_message_id} to remove")
                    starboard_msg = discord.Object(db_msgs[0].starboard_message_id)
                await self.remove_from_starboard(config, starboard_msg, True)

        self.locked_messages.remove(msg)

    @Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Raw API event for reaction add, passes event to action handler"""
        await self.on_raw_reaction_action(payload)

    @Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        """Raw API event for reaction remove, passes event to action handler"""
        await self.on_raw_reaction_action(payload)

    async def on_raw_reaction_action(self, payload: discord.RawReactionActionEvent):
        """Convert the payload into a reaction event and pass the reaction event onto our handler"""
        for msg in self.bot.cached_messages:
            if msg.id == payload.message_id:
                message = msg
                break
        else:
            channel = self.bot.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)

        emoji = str(payload.emoji)
        matching_reaction = [reaction for reaction in message.reactions if str(reaction.emoji) == emoji]

        member = payload.member or message.author
        if len(matching_reaction):
            await self.starboard_check(matching_reaction[0], member)
        else:
            DOZER_LOGGER.debug(f"Unable to find reaction for message({message.id})")

    @guild_only()
    @group(invoke_without_command=True, aliases=['hof'])
    async def starboard(self, ctx: DozerContext):
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

    @guild_only()
    @starboard.command()
    async def showconfig(self, ctx: DozerContext):
        """Show the current server's starboard configuration.
         A starboard (or a hall of fame) is a channel the bot will repost messages in if they receive a certain number\
         of configured reactions.

         To configure a starboard, use the `starboard config` subcommand.
         """
        await self.starboard(ctx)

    @guild_only()
    @has_permissions(manage_guild=True, manage_channels=True)
    @bot_has_permissions(add_reactions=True, embed_links=True)
    @starboard.command()
    async def config(self, ctx: DozerContext, channel: discord.TextChannel,
                     star_emoji: discord.Emoji,
                     threshold: int, cancel_emoji: discord.Emoji = None):
        """Modify the settings for this server's starboard"""
        if str(star_emoji) == str(cancel_emoji):
            await ctx.send("The Star Emoji and Cancel Emoji cannot be the same!")
            return
        for emoji in [emoji for emoji in [star_emoji, cancel_emoji] if emoji is not None]:
            try:
                # try adding it to make sure it's a real emoji. This covers both custom emoijs & unicode emojis
                await ctx.message.add_reaction(emoji)
                await ctx.message.remove_reaction(emoji, ctx.guild.me)
                if isinstance(emoji, discord.Emoji) and emoji.guild_id != ctx.guild.id:
                    await ctx.send(f"The emoji {emoji} is a custom emoji not from this server!")
                    return
            except discord.HTTPException:
                await ctx.send(f"{ctx.author.mention}, bad argument: '{emoji}' is not an emoji, or isn't from a server "
                               f"{ctx.me.name} is in.")
                return

        config: StarboardConfig = StarboardConfig(guild_id=ctx.guild.id, channel_id=channel.id, star_emoji=str(star_emoji),
                                 threshold=threshold, cancel_emoji=str(cancel_emoji))
        await config.update_or_add()
        self.config_cache.invalidate_entry(guild_id=ctx.guild.id)

        await ctx.send(embed=self.make_config_embed(ctx, "Update Starboard config", config))

    config.example_usage = """
    `{prefix}starboard config #hall-of-fame 🌟 5` - Set the bot to repost messages that have 5 star reactions to `#hall-of-fame
    `{prefix}starboard config #hall-of-fame 🌟 5 ❌` - Same as above, but with a extra X cancel emoji 
    """

    @guild_only()
    @has_permissions(manage_guild=True, manage_channels=True)
    @starboard.command()
    async def disable(self, ctx: DozerContext):
        """Turn off the starboard if it is enabled"""
        config: List[StarboardConfig] = await StarboardConfig.get_by(guild_id=ctx.guild.id)
        if not config:
            await ctx.send("There is not a Starboard set up for this server.")
            return

        await StarboardConfig.delete(guild_id=ctx.guild.id)
        self.config_cache.invalidate_entry(guild_id=ctx.guild.id)
        await ctx.send("Starboard disabled for this server.")

    disable.example_usage = """
    `{prefix}starboard disable` - disables the starboard for the current server
    """

    @guild_only()
    @has_permissions(manage_messages=True)
    @starboard.command()
    async def add(self, ctx: DozerContext, message_id: str, channel: discord.TextChannel = None):
        """Add a message to the starboard manually"""
        message_id: int = int(message_id)
        config: StarboardConfig = await self.config_cache.query_one(guild_id=ctx.guild.id)

        if config is None:
            await ctx.send(f"There is not a Starboard configured for this server. Set one up with "
                           f"`{ctx.prefix}starboard config`")
            return
        if channel is None:
            channel = ctx.channel

        try:
            msg: discord.Message = await channel.fetch_message(message_id)
            for reaction in msg.reactions:
                if str(reaction) != config.star_emoji:
                    await self.send_to_starboard(config, msg, reaction.count, False)
                    break
            else:
                await self.send_to_starboard(config, msg, 0, False)
        except discord.NotFound:
            await ctx.send(f"Message {message_id} not found in {channel.mention}")
            return

        await ctx.send(f"Successfully posted message {message_id} to the starboard!")

    add.example_usage = """
    `{prefix}starboard add 1285719825125 #channel` - add message with id `1285719825125` in `#channel` to the starboard 
    manually.
    """


async def setup(bot):
    """Add this cog to the bot"""
    await bot.add_cog(Starboard(bot))


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

    def __init__(self, guild_id: int, channel_id: int, star_emoji: str, threshold: int, cancel_emoji: Optional[str] = None):
        super().__init__()
        self.guild_id: int = guild_id
        self.channel_id: int = channel_id
        self.star_emoji: str = star_emoji
        self.cancel_emoji: Optional[str] = cancel_emoji
        self.threshold: int = threshold

    @classmethod
    async def get_by(cls, **kwargs) -> List["StarboardConfig"]:
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

    def __init__(self, message_id: int, channel_id: int, starboard_message_id: int, author_id: int):
        super().__init__()
        self.message_id: int = message_id
        self.channel_id: int = channel_id
        self.starboard_message_id: int = starboard_message_id
        self.author_id: int = author_id

    @classmethod
    async def get_by(cls, **kwargs) -> List["StarboardMessage"]:
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = StarboardMessage(message_id=result.get("message_id"),
                                   channel_id=result.get("channel_id"),
                                   starboard_message_id=result.get("starboard_message_id"),
                                   author_id=result.get('author_id'))
            result_list.append(obj)
        return result_list
