from discord.ext.commands import has_permissions, bot_has_permissions
from .. import db
from ._utils import *
import discord


class Moderation(Cog):
	@command()
	@has_permissions(ban_members=True)
	@bot_has_permissions(ban_members=True)
	async def ban(self, ctx, user_mentions: discord.User, *, reason):
		"""Bans the user mentioned."""
		usertoban = user_mentions
		howtounban = "When it's time to unban, here's the ID to unban: <@{} >".format(usertoban.id)
		modlogmessage = "{} has been banned by {} because {}. {}".format(usertoban, ctx.author.mention, reason, howtounban)
		await ctx.guild.ban(usertoban)
		await ctx.send(modlogmessage)
		with db.Session() as session:
			modlogchannel = session.query(Guildmodlog).filter_by(id=ctx.guild.id).one_or_none()
			if modlogchannel is not None:
				channel = ctx.guild.get_channel(modlogchannel.modlog_channel)
				await channel.send(modlogmessage)
			else:
				await ctx.send("Please configure modlog channel to enable modlog functionality")

	ban.example_usage = """
	`{prefix}ban @cooldude#1234 he is too good at life` - Will ban Cooldude because "he is too good at life."
	"""
	
	@command()
	@has_permissions(ban_members=True)
	@bot_has_permissions(ban_members=True)
	async def unban(self, ctx, user_mentions: discord.User, *, reason):
		"""Unbans the user ID mentioned."""
		usertoban = user_mentions
		await ctx.guild.unban(usertoban)
		modlogmessage = "{} has been unbanned by {} because {}".format(usertoban, ctx.author.mention, reason)
		await ctx.send(modlogmessage)
		with db.Session() as session:
			modlogchannel = session.query(Guildmodlog).filter_by(id=ctx.guild.id).one_or_none()
			if modlogchannel is not None:
				channel = ctx.guild.get_channel(modlogchannel.modlog_channel)
				await channel.send(modlogmessage)
			else:
				await ctx.send("Please configure modlog channel to enable modlog functionality")

	unban.example_usage = """
	`{prefix}unban 326749693969301506 he stopped being so good at life.` - Will unban Cooldude (id: 326749693969301506) because "he stopped being so good at life."
	"""
	
	@command()
	@has_permissions(kick_members=True)
	@bot_has_permissions(kick_members=True)
	async def kick(self, ctx, user_mentions: discord.User, *, reason):
		"""Kicks the user mentioned."""
		usertokick = user_mentions
		await ctx.guild.kick(usertokick)
		modlogmessage = "{} has been kicked by {} because {}".format(usertokick, ctx.author.mention, reason)
		await ctx.send(modlogmessage)
		with db.Session() as session:
			modlogchannel = session.query(Guildmodlog).filter_by(id=ctx.guild.id).one_or_none()
			if modlogchannel is not None:
				channel = ctx.guild.get_channel(modlogchannel.modlog_channel)
				await channel.send(modlogmessage)
			else:
				await ctx.send("Please configure modlog channel to enable modlog functionality")

	kick.example_usage = """
	`{prefix}kick @cooldude#1234 he froze the server.` - Will kick Cooldude because "he froze the server."
	"""
	
	@command()
	@has_permissions(administrator=True)
	async def config(self, ctx, channel_mentions: discord.TextChannel):
		"""Set the modlog channel for a server by passing the channel through mention, id, or name"""
		print(channel_mentions)
		with db.Session() as session:
			config = session.query(Guildmodlog).filter_by(id=str(ctx.guild.id)).one_or_none()
			if config is not None:
				print("config is not none")
				config.name = ctx.guild.name
				config.modlog_channel = str(channel_mentions.id)
			else:
				print("Config is none")
				config = Guildmodlog(id=ctx.guild.id, modlog_channel=channel_mentions.id, name=ctx.guild.name)
				session.add(config)
			await ctx.send(ctx.message.author.mention + ', modlog settings configured!')

	config.example_usage = """
	`{prefix}config #mod_log` - Will set the modlog channel of the server to the #mod_log channel
	"""

	@command(aliases=["purge"])
	@has_permissions(manage_messages=True)
	@bot_has_permissions(manage_messages=True, read_message_history=True)
	async def prune(self, ctx, num_to_delete: int):
		"""Bulk delete a set number of messages from the current channel."""
		await ctx.message.channel.purge(limit=num_to_delete + 1)
		await ctx.send("Deleted {n} messages under request of {user}".format(n=num_to_delete, user=ctx.message.author.mention), delete_after=5)
	prune.example_usage = """
	`{prefix}prune 10` - Delete the last 10 messages in the current channel.
	"""

class Guildmodlog(db.DatabaseObject):
	__tablename__ = 'modlogconfig'
	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String)
	modlog_channel = db.Column(db.Integer)

def setup(bot):
	bot.add_cog(Moderation(bot))
