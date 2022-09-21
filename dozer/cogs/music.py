"""Music commands, currently disabled"""
import lavaplayer
from discord.ext import commands
from loguru import logger

from dozer.cogs._utils import command


class Music(commands.Cog):
    """Music commands cog"""

    def __init__(self, bot):
        self.bot = bot
        if not self.bot.config['lavalink']['enabled']:
            return

        llconfig = self.bot.config['lavalink']
        self.lavalink = lavaplayer.Lavalink(
            host=llconfig['host'],
            port=llconfig['port'],
            password=llconfig['password'],
        )
        self.lavalink.set_user_id(bot.user.id)
        self.lavalink.connect()

    @command()
    async def disconnect(self, ctx: commands.Context):
        """Disconnects from voice channel"""
        await ctx.guild.change_voice_state(channel=None)
        await self.lavalink.wait_for_remove_connection(ctx.guild.id)
        await ctx.send("Left the voice channel.")

    async def join(self, ctx: commands.Context):
        """Joins the voice channel"""
        print(ctx.author.voice)
        await ctx.guild.change_voice_state(channel=ctx.author.voice.channel, self_deaf=True, self_mute=False)
        print("Awaiting connection")
        await self.lavalink.wait_for_connection(ctx.guild.id)
        print("Join successful")

    @command()
    async def play(self, ctx: commands.Context, *, query: str):
        """Plays a song"""
        await self.join(ctx)
        tracks = await self.lavalink.auto_search_tracks(query)

        if not tracks:
            return await ctx.send("No results found.")
        elif isinstance(tracks, lavaplayer.TrackLoadFailed):
            await ctx.send("Track load failed. Try again.\n```" + tracks.message + "```")
        # Playlist
        elif isinstance(tracks, lavaplayer.PlayList):
            msg = await ctx.send("Playlist found, Adding to queue, Please wait...")
            await self.lavalink.add_to_queue(ctx.guild.id, tracks.tracks, ctx.author.id)
            await msg.edit(content="Added to queue, tracks: {}, name: {}".format(len(tracks.tracks), tracks.name))
            return
        await self.lavalink.wait_for_connection(ctx.guild.id)
        await self.lavalink.play(ctx.guild.id, tracks[0], ctx.author.id)
        await ctx.send(f"Now playing: {tracks[0].title}")

    @command()
    async def pause(self, ctx: commands.Context):
        """Pauses the current song"""
        await self.lavalink.pause(ctx.guild.id, True)
        await ctx.send("Paused the track.")

    @command()
    async def resume(self, ctx: commands.Context):
        """Resume the current song"""
        await self.lavalink.pause(ctx.guild.id, False)
        await ctx.send("Resumed the track.")

    @command()
    async def stop(self, ctx: commands.Context):
        """Stop the current song"""
        await self.lavalink.stop(ctx.guild.id)
        await ctx.send("Stopped the track.")

    @command()
    async def skip(self, ctx: commands.Context):
        """Skip the current song"""
        await self.lavalink.skip(ctx.guild.id)
        await ctx.send("Skipped the track.")

    @command()
    async def queue(self, ctx: commands.Context):
        """Get queue info"""
        queue = await self.lavalink.queue(ctx.guild.id)
        if not queue:
            return await ctx.send("No tracks in queue.")
        tracks = [f"**{i + 1}.** {t.title}" for (i, t) in enumerate(queue)]
        await ctx.send("\n".join(tracks))

    @command()
    async def volume(self, ctx: commands.Context, volume: int):
        """Set the volume"""
        await self.lavalink.volume(ctx.guild.id, volume)
        await ctx.send(f"Set the volume to {volume}%.")

    @command()
    async def seek(self, ctx: commands.Context, seconds: int):
        """Seek to a timestamp in the current song"""
        await self.lavalink.seek(ctx.guild.id, seconds)
        await ctx.send(f"Seeked to {seconds} seconds.")

    @command()
    async def shuffle(self, ctx: commands.Context):
        """Shuffle the queue"""
        await self.lavalink.shuffle(ctx.guild.id)
        await ctx.send("Shuffled the queue.")

    @command()
    async def remove(self, ctx: commands.Context, index: int):
        """Removes a song from the queue"""
        await self.lavalink.remove(ctx.guild.id, index)
        await ctx.send(f"Removed track {index}.")

    @command()
    async def clear(self, ctx: commands.Context):
        """Clears the queue"""
        await self.lavalink.stop(ctx.guild.id)
        await ctx.send("Cleared the queue.")

    @command()
    async def repeat(self, ctx: commands.Context, status: bool):
        """Repeats the queue"""
        await self.lavalink.repeat(ctx.guild.id, status)
        await ctx.send("Repeated the queue.")


async def setup(bot: commands.Bot):
    """Adds the cog to the bot"""
    # await bot.add_cog(Music(bot))
    logger.info("Music cog is temporarily disabled due to code bugs.")
