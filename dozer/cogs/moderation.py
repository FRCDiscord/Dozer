from ._utils import *
import discord

class Moderation(Cog):
    @command()
    async def ban(self, ctx, user_mentions: discord.User):
        "Bans the user mentioned."
        usertoban = user_mentions
        usertobanstr = str(usertoban)
        print("Ban detected for user", usertobanstr)
        await ctx.guild.ban(usertoban)
        await ctx.send(usertobanstr + " has been banned.")
    @command()
    async def unban(self, ctx, user_mentions: discord.User):
        "Unbans the user ID mentioned."
        usertoban = user_mentions
        usertobanstr = str(usertoban)
        print("Unban detected for user" + usertobanstr)
        print(usertoban)
        await ctx.guild.unban(usertoban)
        await ctx.send(usertobanstr + "has been unbanned")
    @command()
    async def kick(self, ctx, user_mentions: discord.User):
        "Kicks the user mentioned."
        haspermissions = ctx.channel.permissions_for(ctx.message.author)
        print(haspermissions)
        usertokick = user_mentions
        await ctx.guild.kick(usertokick)
        await ctx.send(usertokickstr + " has been kicked")
def setup(bot):
    bot.add_cog(Moderation(bot))
