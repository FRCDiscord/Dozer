"""Cog to post specific 'Hall of Fame' messages in a specific channel"""
import datetime

import discord
import typing
from discord.ext.commands import guild_only

from ._utils import *
from .. import db


async def is_cancelled(config, message, me, author=None):
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


def starboard_embed_footer(emoji=None, reaction_count=None):
    """create the footer for a starboard embed"""
    if emoji and reaction_count:
        return f"{reaction_count} {'reactions' if emoji.startswith('<') else emoji} | "
    else:
        return ""


def make_starboard_embed(msg: discord.Message):
    """Makes a starboard embed."""
    e = discord.Embed(color=discord.Color.gold())
    e.set_author(name=msg.author.display_name, icon_url=msg.author.avatar_url)
    if len(msg.content):
        e.description = msg.content

    # Open question: how do we deal with attachment posts that aren't just an image?
    if len(msg.attachments) > 1:
        e.add_field(name="Attachments:", value="\n".join([a.url for a in msg.attachments[1:]]))
    if len(msg.attachments) == 1:
        if hasattr(msg.attachments[0], 'width'):
            e.set_image(url=msg.attachments[0].url)
        else:
            e.add_field(name="Attachment:", value=msg.attachments[0].url)

    e.add_field(name="Jump link", value=f"[here]({msg.jump_url})")

    e.set_footer(text=str(msg.guild))  # self.starboard_embed_footer(emoji, reaction_count) + str(msg.guild))
    e.timestamp = datetime.datetime.utcnow()
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

    async def send_to_starboard(self, config, message):
        starboard_channel = message.guild.get_channel(config.channel_id)
        if starboard_channel is None:
            return
        await starboard_channel.send("Test!")

    async def remove_from_starboard(self, config, message):
        print("Removed!")

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
            await self.send_to_starboard(config, msg)

    @Cog.listener()
    async def on_reaction_add(self, reaction, user):
        await self.starboard_check(reaction, user)

    @Cog.listener()
    async def on_reaction_remove(self, reaction, user):
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

    @starboard.command()
    async def config(self, ctx, channel: discord.TextChannel, star_emoji: typing.Union[discord.Emoji, str],
                     threshold: int,
                     cancel_emoji: typing.Union[discord.Emoji, str] = None):
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

    @starboard.command()
    async def disable(self, ctx):
        config = await StarboardConfig.get_by(guild_id=ctx.guild.id)
        if not config:
            await ctx.send("There is not Starboard set up for this server.")
            return

        await config[0].delete()
        try:
            del self.config_cache[ctx.guild]
        except KeyError:
            pass

        await ctx.send("Starboard disabled for this server.")


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
            starboard_message_id bigint NOT NULL,
            author_id bigint NOT NULL
            )""")

    def __init__(self, message_id, starboard_message_id, author_id):
        super().__init__()
        self.message_id = message_id
        self.starboard_message_id = starboard_message_id
        self.author_id = author_id

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = StarboardMessage(message_id=result.get("message_id"),
                                   starboard_message_id=result.get("starboard_message_id"),
                                   author_id=result.get('author_id'))
            result_list.append(obj)
        return result_list
