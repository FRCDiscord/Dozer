from discord.ext.commands import has_permissions, bot_has_permissions

from ._utils import *
import discord

class Moderation(Cog):
	"""
	Moderation commands for simplifying and improving Discord's moderation tools.
	These commands are restricted to users who have permission to do the action manually.
	For example, the ban and unban commands require permission to ban members.
	"""
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
		await ctx.send(usertobanstr + " has been banned.")
		howtounban = "When it's time to unban, here's the ID to unban: <@" + bannedid + " >"
		await ctx.send(howtounban)
	
	ban.example_usage = """
	`{prefix}ban cooldude#1234` - Bans cooldude
	"""
	
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
	
	unban.example_usage = """
	`{prefix}unban cooldude#1234` - Unbans cooldude
	"""
	
	@command()
	@has_permissions(kick_members=True)
	@bot_has_permissions(kick_members=True)
	async def kick(self, ctx, user_mentions: discord.User):
		"""
		Kicks the user mentioned.
		This does not prevent the user from rejoining.
		If there is a public invite to your server, the user may rejoin.
		"""
		usertokick = user_mentions
		usertokickstr = str(usertokick)
		await ctx.guild.kick(usertokick)
		await ctx.send(usertokickstr + " has been kicked")
	
	kick.example_usage = """
	`{prefix}kick cooldude#1234` - Kicks cooldude
	"""

def setup(bot):
	bot.add_cog(Moderation(bot))
