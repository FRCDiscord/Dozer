from discord.ext.commands import has_permissions, bot_has_permissions
from .. import db
from ._utils import *
import discord


class Moderation(Cog):
	def __init__(self, bot):
		super().__init__(bot)
	@command()
	@has_permissions(ban_members=True)
	@bot_has_permissions(ban_members=True)
	async def ban(self, ctx, user_mentions: discord.User, *, reason):
		"Bans the user mentioned."
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
	
	@command()
	@has_permissions(ban_members=True)
	@bot_has_permissions(ban_members=True)
	async def unban(self, ctx, user_mentions: discord.User, *, reason):
		"Unbans the user ID mentioned."
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
	
	@command()
	@has_permissions(kick_members=True)
	@bot_has_permissions(kick_members=True)
	async def kick(self, ctx, user_mentions: discord.User, *, reason):
		"Kicks the user mentioned."
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
	
	@command()
	@has_permissions(administrator=True)
	async def config(self, ctx, channel_mentions: discord.TextChannel):
		"""Set the modlog channel for a server by passing the channel id"""
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

	async def on_message(self, message):
		if message.author.bot: return
		if not message.guild.me.guild_permissions.manage_roles: return

		with db.Session() as session:
			config = session.query(GuildNewMemmber).filter_by(guild_id=message.guild.id).one_or_none()
			if config is not None:
				string = config.message
				content = message.content.casefold()
				if string not in content: return
				channel = config.channel_id
				role_id = config.role_id
				if message.channel.id != channel: return
				await message.author.add_roles(discord.utils.get(message.guild.roles, id=role_id))

	@command()
	#@has_permissions(administrator=True)
	async def nmconfig(self, ctx, channel_mentions: discord.TextChannel, role_id: discord.Role, *, message):
		"""Set the config for the new members channel"""
		with db.Session() as session:
			config = session.query(GuildNewMemmber).filter_by(guild_id=ctx.guild.id).one_or_none()
			if config is not None:
				config.channel_id = channel_mentions.id
				config.role_id = role_id.id
				config.message = message.casefold()
				role_name = role_id.name
				await ctx.send("New Member Channel configured as: {channel}. Role configured as: {role}. Message: {message}".format(channel=ctx.channel.name, role=role_name, message=message))
			else:
				config = GuildNewMemmber(guild_id=ctx.guild.id, channel_id=channel_mentions.id, role_id=role_id.id, message=message.casefold())
				session.add(config)
				role_name = role_id.name
				await ctx.send("New Member Channel configured as: {channel}. Role configured as: {role}. Message: {message}".format(channel=ctx.channel.name, role=role_name, message=message))

class Guildmodlog(db.DatabaseObject):
	__tablename__ = 'modlogconfig'
	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String)
	modlog_channel = db.Column(db.Integer)

class GuildNewMemmber(db.DatabaseObject):
	__tablename__ = 'new_members'
	guild_id = db.Column(db.Integer, primary_key=True)
	channel_id = db.Column(db.Integer)
	role_id = db.Column(db.Integer)
	message = db.Column(db.String)

def setup(bot):
	bot.add_cog(Moderation(bot))
