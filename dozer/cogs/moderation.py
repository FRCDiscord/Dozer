from ._utils import *
import discord

class Moderation(Cog):
    @command()
    async def ban(self, ctx, user_mentions: discord.User):
        "Bans the user mentioned."
        usertoban = user_mentions
        usertobanstr = str(usertoban)
        reason = ctx.message.content.split(" ", maxsplit=2)[2]
        print("Ban detected for user", usertobanstr)
        await ctx.guild.ban(usertoban)
        await ctx.send(usertobanstr + " has been banned.\nReason: **" + reason + "**")
    @command()
    async def unban(self, ctx, user_mentions: discord.User):
        "Unbans the user ID mentioned."
        usertoban = user_mentions
        usertobanstr = str(usertoban)
        reason = ctx.message.content.split(" ", maxsplit=2)[2]
        print("Unban detected for user" + usertobanstr)
        await ctx.guild.unban(usertoban)
        await ctx.send(usertobanstr + "has been unbanned.\nReason: **" + reason + "**")
    @command()
    async def kick(self, ctx, user_mentions: discord.User):
        "Kicks the user mentioned."
        usertokick = user_mentions
        usertokickstr = str(usertokick)
        reason = ctx.message.content.split(" ", maxsplit=2)[2]
        await ctx.guild.kick(usertokick)
        await ctx.send(usertokickstr + " has been kicked.\nReason: **" + reason + "**")
def setup(bot):
    bot.add_cog(Moderation(bot))
