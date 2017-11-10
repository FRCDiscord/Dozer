import asyncio, discord
from discord.ext.commands import BadArgument, has_permissions, bot_has_permissions, RoleConverter
from .. import db
from ._utils import *


class SafeRoleConverter(RoleConverter):
	async def convert(self, ctx, arg):
		try:
			return await super().convert(ctx, arg)
		except BadArgument:
			if arg.casefold() in ('everyone', '@everyone', '@/everyone', '@.everyone', '@ everyone', '@\N{ZERO WIDTH SPACE}everyone'):
				return ctx.guild.default_role
			else:
				raise


# Todo: timed/self mutes
class Moderation(Cog):
	async def permoverride(self, user, **overwrites):
		for i in user.guild.channels:
			overwrite = i.overwrites_for(user)
			for x in overwrites:
				print(x)
				overwrite.update(x)
			print(overwrite)
			await overwrite.update()

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

	async def on_message(self, message):
		if message.author.bot: return
		if not message.guild.me.guild_permissions.manage_roles: return

		with db.Session() as session:
			config = session.query(GuildNewMember).filter_by(guild_id=message.guild.id).one_or_none()
			if config is not None:
				string = config.message
				content = message.content.casefold()
				if string not in content: return
				channel = config.channel_id
				role_id = config.role_id
				if message.channel.id != channel: return
				await message.author.add_roles(discord.utils.get(message.guild.roles, id=role_id))

	@command()
	@has_permissions(administrator=True)
	async def nmconfig(self, ctx, channel_mention: discord.TextChannel, role: discord.Role, *, message):
		"""Sets the config for the new members channel"""
		with db.Session() as session:
			config = session.query(GuildNewMember).filter_by(guild_id=ctx.guild.id).one_or_none()
			if config is not None:
				config.channel_id = channel_mention.id
				config.role_id = role.id
				config.message = message.casefold()
			else:
				config = GuildNewMember(guild_id=ctx.guild.id, channel_id=channel_mention.id, role_id=role.id, message=message.casefold())
				session.add(config)

		role_name = role.name
		await ctx.send("New Member Channel configured as: {channel}. Role configured as: {role}. Message: {message}".format(channel=ctx.channel.name, role=role_name, message=message))

	nmconfig.example_usage = """
	`{prefix}nmconfig #new_members Member I have read the rules and regulations` - Configures the #new_members channel so if someone types "I have read the rules and regulations" it assigns them the Member role. 
	"""
	

	@command()
	@has_permissions(manage_roles=True)
	@bot_has_permissions(manage_roles=True)
	async def timeout(self, ctx, duration: float):
		"""Set a timeout (no sending messages or adding reactions) on the current channel."""
		with db.Session() as session:
			settings = session.query(MemberRole).filter_by(id=ctx.guild.id).one_or_none()
			if settings is None:
				settings = MemberRole(id=ctx.guild.id)
				session.add(settings)
			
			member_role = discord.utils.get(ctx.guild.roles, id=settings.member_role) # None-safe - nonexistent or non-configured role return None
		
		if member_role is not None:
			targets = {member_role}
		else:
			await ctx.send('{0.author.mention}, the members role has not been configured. This may not work as expected. Use `{0.prefix}help memberconfig` to see how to set this up.'.format(ctx))
			targets = set(sorted(ctx.guild.roles)[:ctx.author.top_role.position])
		
		to_restore = [(target, ctx.channel.overwrites_for(target)) for target in targets]
		for target, overwrite in to_restore:
			new_overwrite = discord.PermissionOverwrite.from_pair(*overwrite.pair())
			new_overwrite.update(send_messages=False, add_reactions=False)
			await ctx.channel.set_permissions(target, overwrite=new_overwrite)
		
		for allow_target in (ctx.me, ctx.author):
			overwrite = ctx.channel.overwrites_for(allow_target)
			new_overwrite = discord.PermissionOverwrite.from_pair(*overwrite.pair())
			new_overwrite.update(send_messages=True)
			await ctx.channel.set_permissions(allow_target, overwrite=new_overwrite)
			to_restore.append((allow_target, overwrite))
		
		e = discord.Embed(title='Timeout - {}s'.format(duration), description='This channel has been timed out.', color=discord.Color.blue())
		e.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url_as(format='png', size=32))
		msg = await ctx.send(embed=e)
		
		await asyncio.sleep(duration)
		
		for target, overwrite in to_restore:
			if all(permission is None for _, permission in overwrite):
				await ctx.channel.set_permissions(target, overwrite=None)
			else:
				await ctx.channel.set_permissions(target, overwrite=overwrite)
		
		e.description = 'The timeout has ended.'
		await msg.edit(embed=e)
	
	timeout.example_usage = """
	`{prefix}timeout 60` - prevents sending messages in this channel for 1 minute (60s)
	"""
	
	@command()
	@has_permissions(administrator=True)
	async def memberconfig(self, ctx, *, member_role: SafeRoleConverter):
		"""
		Set the member role for the guild.
		The member role is the role used for the timeout command. It should be a role that all members of the server have.
		"""
		if member_role >= ctx.author.top_role:
			raise BadArgument('member role cannot be higher than your top role!')
		
		with db.Session() as session:
			settings = session.query(MemberRole).filter_by(id=ctx.guild.id).one_or_none()
			if settings is None:
				settings = MemberRole(id=ctx.guild.id, member_role=member_role.id)
				session.add(settings)
			else:
				settings.member_role = member_role.id
		await ctx.send('Member role set as `{}`.'.format(member_role.name))
	
	memberconfig.example_usage = """
	`{prefix}memberconfig Members` - set a role called "Members" as the member role
	`{prefix}memberconfig @everyone` - set the default role as the member role
	`{prefix}memberconfig everyone` - set the default role as the member role (ping-safe)
	`{prefix}memberconfig @ everyone` - set the default role as the member role (ping-safe)
	`{prefix}memberconfig @.everyone` - set the default role as the member role (ping-safe)
	`{prefix}memberconfig @/everyone` - set the default role as the member role (ping-safe)
	"""
	
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
		memberjoinedmessage = "{} has joined the server! Enjoy your stay! This server now has {}".format(member.display_name, len(member.guild.members))
		with db.Session() as session:
			memberlogchannel = session.query(Guildmemberlog).filter_by(id=member.guild.id).one_or_none()
			if memberlogchannel is not None:
				channel = member.guild.get_channel(memberlogchannel.memberlog_channel)
				await channel.send(memberjoinedmessage)
			user = session.query(Guildmute).filter_by(id=member.id).one_or_none()
			if user is not None and user.guild == member.guild.id:
				await self.permoverride(user, add_reactions=False, send_messages=False)
			user = session.query(Deafen).filter_by(id=member.id).one_or_none()
			if user is not None and user.guild == member.guild.id:
				await self.permoverride(user, read_messages=False)

	async def on_member_remove(self, member):
		memberleftmessage = "{} has left the server! This server now has {} members".format(member.display_name, len(member.guild.members))
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
		e.add_field(name='Author pingable', value=message.author.mention)
		e.add_field(name='Channel', value=message.channel)
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
			e.add_field(name='Author pingable', value=before.author.mention)
			e.add_field(name='Channel', value=before.channel)
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
	async def mute(self, ctx, member_mentions: discord.Member, *, reason="No reason provided"):
		await self.permoverride(member_mentions, send_messages=False, add_reactions=False)
		modlogmessage = "{} has been muted by {} because {}".format(member_mentions, ctx.author.display_name, reason)
		await ctx.send(modlogmessage)
		with db.Session() as session:
			modlogchannel = session.query(Guildmodlog).filter_by(id=ctx.guild.id).one_or_none()
			if modlogchannel is not None:
				channel = ctx.guild.get_channel(modlogchannel.modlog_channel)
				await channel.send(modlogmessage)
			else:
				await ctx.send("Please configure modlog channel to enable modlog functionality")
			user = session.query(Guildmute).filter_by(id=member_mentions.id).one_or_none()
			if user is not None:
				Guildmute.id = str(member_mentions.id)
				Guildmute.guild = str(ctx.guild.id)
			else:
				user = Guildmute(id=member_mentions.id, guild=ctx.guild.id)
				session.add(user)


	@command()
	@has_permissions(kick_members=True)
	@bot_has_permissions(manage_roles=True)
	async def unmute(self, ctx, member_mentions: discord.Member):
		await self.permoverride(member_mentions, send_messages=None, add_reactions=None)
		modlogmessage = "{} has been unmuted by {}".format(member_mentions, ctx.author.display_name)
		await ctx.send(modlogmessage)
		with db.Session() as session:
			modlogchannel = session.query(Guildmodlog).filter_by(id=ctx.guild.id).one_or_none()
			if modlogchannel is not None:
				channel = ctx.guild.get_channel(modlogchannel.modlog_channel)
				await channel.send(modlogmessage)
			else:
				await ctx.send("Please configure modlog channel to enable modlog functionality")
			user = session.query(Guildmute).filter_by(id=member_mentions.id).one_or_none()
			if user is not None:
				session.delete(user)
			else:
				await ctx.send("User is not muted!")

	@command()
	@has_permissions(kick_members=True)
	@bot_has_permissions(manage_roles=True)
	async def deafen(self, ctx, member_mentions: discord.Member, *, reason="No reason provided"):
		await self.permoverride(member_mentions, read_messages=False)
		modlogmessage = "{} has been deafened by {} because {}".format(member_mentions, ctx.author.display_name, reason)
		await ctx.send(modlogmessage)
		with db.Session() as session:
			modlogchannel = session.query(Guildmodlog).filter_by(id=ctx.guild.id).one_or_none()
			if modlogchannel is not None:
				channel = ctx.guild.get_channel(modlogchannel.modlog_channel)
				await channel.send(modlogmessage)
			else:
				await ctx.send("Please configure modlog channel to enable modlog functionality")
			user = session.query(Deafen).filter_by(id=member_mentions.id).one_or_none()
			if user is not None:
				Deafen.id = str(member_mentions.id)
				Deafen.guild = str(ctx.guild.id)
			else:
				user = Deafen(id=member_mentions.id, guild=ctx.guild.id)
				session.add(user)

	@command()
	@has_permissions(kick_members=True)
	@bot_has_permissions(manage_roles=True)
	async def undeafen(self, ctx, member_mentions: discord.Member):
		await self.permoverride(member_mentions, read_messages=None)
		modlogmessage = "{} has been undeafened by {}".format(member_mentions, ctx.author.display_name)
		await ctx.send(modlogmessage)
		with db.Session() as session:
			modlogchannel = session.query(Guildmodlog).filter_by(id=ctx.guild.id).one_or_none()
			if modlogchannel is not None:
				channel = ctx.guild.get_channel(modlogchannel.modlog_channel)
				await channel.send(modlogmessage)
			else:
				await ctx.send("Please configure modlog channel to enable modlog functionality")
			user = session.query(Deafen).filter_by(id=member_mentions.id).one_or_none()
			if user is not None:
				session.delete(user)
			else:
				await ctx.send("User is not deafened!")


class Guildmute(db.DatabaseObject):
	__tablename__ = 'Mutes'
	id = db.Column(db.String, primary_key=True)
	guild = db.Column(db.String)


class Deafen(db.DatabaseObject):
	__tablename__ = 'Deafens'
	id = db.Column(db.String, primary_key=True)
	guild = db.Column(db.String)


class Guildmodlog(db.DatabaseObject):
	__tablename__ = 'modlogconfig'
	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String)
	modlog_channel = db.Column(db.Integer, nullable=True)

class MemberRole(db.DatabaseObject):
	__tablename__ = 'member_roles'
	id = db.Column(db.Integer, primary_key=True)
	member_role = db.Column(db.Integer, nullable=True)

class GuildNewMember(db.DatabaseObject):
	__tablename__ = 'new_members'
	guild_id = db.Column(db.Integer, primary_key=True)
	channel_id = db.Column(db.Integer)
	role_id = db.Column(db.Integer)
	message = db.Column(db.String)
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
