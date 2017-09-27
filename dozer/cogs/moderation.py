from discord.ext.commands import has_permissions, bot_has_permissions

from ._utils import *
import discord

# Todo for current functions: Logging, reasons, per-server config for moderation channel
class Moderation(Cog):
	@command()
	@has_permissions(ban_members=True)
	@bot_has_permissions(ban_members=True)
	async def ban(self, ctx, user_mentions: discord.User):
		"Bans the user mentioned."
		usertoban = user_mentions
		usertobanstr = str(usertoban)
		bannedid = str(usertoban.id)
		print("Ban detected for user", usertobanstr)
		await ctx.guild.ban(usertoban)
		howtounban = "When it's time to unban, here's the ID to unban: <@" + bannedid + " >"
		await ctx.send(usertobanstr + " has been banned." + howtounban)
	
	@command()
	@has_permissions(ban_members=True)
	@bot_has_permissions(ban_members=True)
	async def unban(self, ctx, user_mentions: discord.User):
		"Unbans the user ID mentioned."
		usertoban = user_mentions
		usertobanstr = str(usertoban)
		print("Unban detected for user" + usertobanstr)
		print(usertoban)
		await ctx.guild.unban(usertoban)
		await ctx.send(usertobanstr + "has been unbanned")
	
	@command()
	@has_permissions(kick_members=True)
	@bot_has_permissions(kick_members=True)
	async def kick(self, ctx, user_mentions: discord.User):
		"Kicks the user mentioned."
		usertokick = user_mentions
		usertokickstr = str(usertokick)
		await ctx.guild.kick(usertokick)
		await ctx.send(usertokickstr + " has been kicked")

def setup(bot):
	bot.add_cog(Moderation(bot))
