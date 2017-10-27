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

class Moderation(Cog):
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
			modlogchannel = session.query(ModerationSettings).filter_by(id=ctx.guild.id).one_or_none()
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
			modlogchannel = session.query(ModerationSettings).filter_by(id=ctx.guild.id).one_or_none()
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
			modlogchannel = session.query(ModerationSettings).filter_by(id=ctx.guild.id).one_or_none()
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
			config = session.query(ModerationSettings).filter_by(id=str(ctx.guild.id)).one_or_none()
			if config is not None:
				print("config is not none")
				config.name = ctx.guild.name
				config.modlog_channel = str(channel_mentions.id)
			else:
				print("Config is none")
				config = ModerationSettings(id=ctx.guild.id, modlog_channel=channel_mentions.id, name=ctx.guild.name)
				session.add(config)
			await ctx.send(ctx.message.author.mention + ', modlog settings configured!')
	
	@command()
	@has_permissions(manage_roles=True)
	@bot_has_permissions(manage_roles=True)
	async def timeout(self, ctx, duration: float):
		"""Set a timeout (no sending messages or adding reactions) on the current channel."""
		with db.Session() as session:
			settings = session.query(ModerationSettings).filter_by(id=ctx.guild.id).one_or_none()
			if settings is None:
				settings = ModerationSettings(id=ctx.guild.id, name=ctx.guild.name)
				session.add(settings)
			
			member_role = discord.utils.get(ctx.guild.roles, id=settings.member_role) # None-safe - nonexistent or non-configured role return None
		
		if member_role is not None:
			targets = {member_role}
		else:
			await ctx.send('{0.author.mention}, the members role has not been configured. This may not work as expected. Use `{0.prefix}help memberconfig` to see how to set this up.'.format(ctx))
			targets = {target for target, overwrite in ctx.channel.overwrites if overwrite.send_messages or overwrite.add_reactions and (target if isinstance(target, discord.Role) else target.top_role) < ctx.me.top_role}
		
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
		with db.Session() as session:
			settings = session.query(ModerationSettings).filter_by(id=ctx.guild.id).one_or_none()
			if settings is None:
				settings = ModerationSettings(id=ctx.guild.id, name=ctx.guild.name, member_role=member_role.id)
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

class ModerationSettings(db.DatabaseObject):
	__tablename__ = 'modlogconfig'
	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String)
	modlog_channel = db.Column(db.Integer, nullable=True)
	member_role = db.Column(db.Integer, nullable=True)

def setup(bot):
	bot.add_cog(Moderation(bot))
