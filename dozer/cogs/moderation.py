from discord.ext.commands import has_permissions, bot_has_permissions
from .. import db
from ._utils import *
import discord

# Todo: timed/self mutes, audit logging reasoning passing
class Moderation(Cog):
	@command()
	@has_permissions(ban_members=True)
	@bot_has_permissions(ban_members=True)
	async def ban(self, ctx, user_mentions: discord.User, *, reason="No reason provided"):
		"Bans the user mentioned."
		usertoban = user_mentions
		howtounban = "When it's time to unban, here's the ID to unban: <@{} >".format(usertoban.id)
		modlogmessage = "{} has been banned by {} because {}. {}".format(usertoban, ctx.author.mention, reason, howtounban)
		await ctx.guild.ban(usertoban, reason=reason)
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
	async def unban(self, ctx, user_mentions: discord.User, *, reason="No reason provided"):
		"Unbans the user ID mentioned."
		usertoban = user_mentions
		await ctx.guild.unban(usertoban, reason=reason)
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
	async def kick(self, ctx, user_mentions: discord.User, *, reason="No reason provided"):
		"Kicks the user mentioned."
		usertokick = user_mentions
		await ctx.guild.kick(usertokick, reason=reason)
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
	async def modlogconfig(self, ctx, channel_mentions: discord.TextChannel):
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
	
	@command()
	@has_permissions(administrator=True)
	async def memberlogconfig(self, ctx, channel_mentions: discord.TextChannel):
		"""Set the modlog channel for a server by passing the channel id"""
		print(channel_mentions)
		with db.Session() as session:
			config = session.query(Guildmemberlog).filter_by(id=str(ctx.guild.id)).one_or_none()
			if config is not None:
				print("config is not none")
				config.name = ctx.guild.name
				config.memberlog_channel = str(channel_mentions.id)
			else:
				print("Config is none")
				config = Guildmemberlog(id=ctx.guild.id, memberlog_channel=channel_mentions.id, name=ctx.guild.name)
				session.add(config)
			await ctx.send(ctx.message.author.mention + ', memberlog settings configured!')
	
	@command()
	@has_permissions(administrator=True)
	async def messagelogconfig(self, ctx, channel_mentions: discord.TextChannel):
		"""Set the modlog channel for a server by passing the channel id"""
		print(channel_mentions)
		with db.Session() as session:
			config = session.query(Guildmessagelog).filter_by(id=str(ctx.guild.id)).one_or_none()
			if config is not None:
				print("config is not none")
				config.name = ctx.guild.name
				config.messagelog_channel = str(channel_mentions.id)
			else:
				print("Config is none")
				config = Guildmessagelog(id=ctx.guild.id, messagelog_channel=channel_mentions.id, name=ctx.guild.name)
				session.add(config)
			await ctx.send(ctx.message.author.mention + ', messagelog settings configured!')
	
	async def on_member_join(self, member):
		memberjoinedmessage = "{} has joined the server! Enjoy your stay!".format(member.display_name)
		with db.Session() as session:
			memberlogchannel = session.query(Guildmemberlog).filter_by(id=member.guild.id).one_or_none()
			if memberlogchannel is not None:
				channel = member.guild.get_channel(memberlogchannel.memberlog_channel)
				await channel.send(memberjoinedmessage)
	
	async def on_member_remove(self, member):
		memberleftmessage = "{} has left the server!".format(member.display_name)
		with db.Session() as session:
			memberlogchannel = session.query(Guildmemberlog).filter_by(id=member.guild.id).one_or_none()
			if memberlogchannel is not None:
				channel = member.guild.get_channel(memberlogchannel.memberlog_channel)
				await channel.send(memberleftmessage)
	
	async def on_message_delete(self, message):
		e = discord.Embed(type='rich')
		e.title = 'Message Deletion'
		e.color = 0xFF0000
		e.add_field(name='Author', value=message.author)
		if 1024 > len(message.content) > 0:
			e.add_field(name="Deleted message", value=message.content)
		elif len(message.content) != 0:
			e.add_field(name="Deleted message", value=message.content[0:1023])
			e.add_field(name="Deleted message continued", value=message.content[1024:2000])
		elif len(message.content) == 0:
			for i in message.embeds:
				e.add_field(name="Title", value=i.title)
				e.add_field(name="Description", value=i.description)
				e.add_field(name="Timestamp", value=i.timestamp)
				for x in i.fields:
					e.add_field(name=x.name, value=x.value)
				e.add_field(name="Footer", value=i.footer)
		with db.Session() as session:
			messagelogchannel = session.query(Guildmessagelog).filter_by(id=message.guild.id).one_or_none()
			if messagelogchannel is not None:
				channel = message.guild.get_channel(messagelogchannel.messagelog_channel)
				await channel.send(embed=e)
	
	async def on_message_edit(self, before, after):
		if after.edited_at is not None or before.edited_at is not None:
			# There is a reason for this. That reason is that otherwise, an infinite spam loop occurs
			e = discord.Embed(type='rich')
			e.title = 'Message Edited'
			e.color = 0xFF0000
			e.add_field(name='Author', value=before.author)
			if 1024 > len(before.content) > 0:
				e.add_field(name="Old message", value=before.content)
			elif len(before.content) != 0:
				e.add_field(name="Old message", value=before.content[0:1023])
				e.add_field(name="Old message continued", value=before.content[1024:2000])
			elif len(before.content) == 0 and before.edited_at is not None:
				for i in before.embeds:
					e.add_field(name="Title", value=i.title)
					e.add_field(name="Description", value=i.description)
					e.add_field(name="Timestamp", value=i.timestamp)
					for x in i.fields:
						e.add_field(name=x.name, value=x.value)
					e.add_field(name="Footer", value=i.footer)
			if 0 < len(after.content) < 1024:
				e.add_field(name="New message", value=after.content)
			elif len(after.content) != 0:
				e.add_field(name="New message", value=after.content[0:1023])
				e.add_field(name="New message continued", value=after.content[1024:2000])
			elif len(after.content) == 0 and after.edited_at is not None:
				e.add_field(name="Title", value=i.title)
				e.add_field(name="Description", value=i.description)
				e.add_field(name="Timestamp", value=i.timestamp)
				for i in after.embeds:
					for x in i.fields:
						e.add_field(name=x.name, value=x.value)
			with db.Session() as session:
				messagelogchannel = session.query(Guildmessagelog).filter_by(id=before.guild.id).one_or_none()
				if messagelogchannel is not None:
					channel = before.guild.get_channel(messagelogchannel.messagelog_channel)
					await channel.send(embed=e)
	
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

    @command()
    @has_permissions(kick_members=True)
    @bot_has_permissions(manage_roles=True)
    async def mute(self, ctx, member_mentions: discord.Member, *, reason):
        for i in ctx.guild.channels:
            overwrite = discord.PermissionOverwrite()
            overwrite.send_messages = False
            overwrite.add_reactions = False
            await i.set_permissions(target=member_mentions, overwrite=overwrite)
        modlogmessage = "{} has been muted by {} because {}".format(member_mentions, ctx.author.display_name, reason)
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
    @bot_has_permissions(manage_roles=True)
    async def unmute(self, ctx, member_mentions: discord.Member):
        for i in ctx.guild.channels:
            await i.set_permissions(target=member_mentions, overwrite=None)
        modlogmessage = "{} has been unmuted by {}".format(member_mentions, ctx.author.display_name)
        await ctx.send(modlogmessage)
        with db.Session() as session:
            modlogchannel = session.query(Guildmodlog).filter_by(id=ctx.guild.id).one_or_none()
            if modlogchannel is not None:
                channel = ctx.guild.get_channel(modlogchannel.modlog_channel)
                await channel.send(modlogmessage)
            else:
                await ctx.send("Please configure modlog channel to enable modlog functionality")


class Guildmodlog(db.DatabaseObject):
	__tablename__ = 'modlogconfig'
	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String)
	modlog_channel = db.Column(db.Integer)

class Guildmemberlog(db.DatabaseObject):
	__tablename__ = 'memberlogconfig'
	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String)
	memberlog_channel = db.Column(db.Integer)

class Guildmessagelog(db.DatabaseObject):
	__tablename__ = 'messagelogconfig'
	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String)
	messagelog_channel = db.Column(db.Integer)

def setup(bot):
	bot.add_cog(Moderation(bot))
