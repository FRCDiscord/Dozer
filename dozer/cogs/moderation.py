from ._utils import *
import discord

class Moderation(Cog):
    @command()
    async def ban(self, ctx, user_mentions: discord.Member):
        usertoban = user_mentions
        usertobanstr = str(usertoban)
        print("Ban detected for user", usertobanstr)
        await ctx.send("Testing! Banning " + usertobanstr)
        #banmember = discord.ext.commands.MemberConverter(usertoban)
        print(usertoban)
        await ctx.guild.ban(usertoban)

def setup(bot):
    bot.add_cog(Moderation(bot))