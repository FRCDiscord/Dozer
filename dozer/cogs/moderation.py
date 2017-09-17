from ._utils import *
import discord

class Moderation(Cog):
    @command()
    async def ban(self, ctx, user_mentions: discord.User):
        usertoban = user_mentions
        usertobanstr = str(usertoban)
        print("Ban detected for user", usertobanstr)
        await ctx.send("Banning " + usertobanstr)
        print(usertoban)
        await ctx.guild.ban(usertoban)
        bannedid = str(user_mentions.id)
        howtounban = "When it's time to unban, run t&unban <@" + bannedid + " >"
        await ctx.send(howtounban)
    @command()
    async def unban(self, ctx, user_mentions: discord.User):
        usertoban = user_mentions
        usertobanstr = str(usertoban)
        print("Unban detected for user", usertobanstr)
        await ctx.send("Unbanning " + usertobanstr)
        print(usertoban)
        await ctx.guild.unban(usertoban)

def setup(bot):
    bot.add_cog(Moderation(bot))