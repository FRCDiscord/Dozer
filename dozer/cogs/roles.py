import discord, discord.utils
from discord.ext.commands import bot_has_permissions, cooldown, BucketType, has_permissions, BadArgument
from sqlalchemy.orm.exc import MultipleResultsFound, NoResultFound
from .. import db
from ._utils import *

class Roles(Cog):
	"""Commands for role management."""
	async def on_member_join(self, member):
		me = member.guild.me
		top_restoreable = me.top_role.position if me.guild_permissions.manage_roles else 0
		with db.Session() as session:
			restore = session.query(MissingMember).filter_by(guild_id=member.guild.id, member_id=member.id).one_or_none()
			if restore is None:
				return # New member - nothing to restore
			
			valid, cant_give, missing = set(), set(), set()
			role_ids = {role.id: role for role in member.guild.roles}
			for missing_role in restore.missing_roles:
				role = role_ids.get(missing_role.role_id)
				if role is None: # Role with that ID does not exist
					missing.add(missing_role.role_name)
				elif role.position > top_restoreable:
					cant_give.add(role.name)
				else:
					valid.add(role)
			
			session.delete(restore) # Not missing anymore - remove the record to free up the primary key
		
		await member.add_roles(*valid)
		if not missing and not cant_give:
			return
		
		e = discord.Embed(title='Welcome back to the {} server, {}!'.format(member.guild.name, member), color=discord.Color.blue())
		if missing:
			e.add_field(name='I couldn\'t restore these roles, as they don\'t exist.', value='\n'.join(sorted(missing)))
		if cant_give:
			e.add_field(name='I couldn\'t restore these roles, as I don\'t have permission.', value='\n'.join(sorted(cant_give)))
		
		send_perms = discord.Permissions()
		send_perms.update(send_messages=True, embed_links=True)
		try:
			dest = next(channel for channel in member.guild.text_channels if channel.permissions_for(me) >= send_perms)
		except StopIteration:
			dest = await member.guild.owner.create_dm()
		
		await dest.send(embed=e)
	
	async def on_member_remove(self, member):
		guild_id = member.guild.id
		member_id = member.id
		with db.Session() as session:
			db_member = MissingMember(guild_id=guild_id, member_id=member_id)
			session.add(db_member)
			for role in member.roles[1:]: # Exclude the @everyone role
				db_member.missing_roles.append(MissingRole(role_id=role.id, role_name=role.name))
	
	@group(invoke_without_command=True)
	@bot_has_permissions(manage_roles=True)
	async def giveme(self, ctx, *, roles):
		"""Give you one or more giveable roles, separated by commas."""
		norm_names = [self.normalize(name) for name in roles.split(',')]
		with db.Session() as session:
			giveable_ids = [tup[0] for tup in session.query(GiveableRole.id).filter(GiveableRole.guild_id == ctx.guild.id, GiveableRole.norm_name.in_(norm_names)).all()]
			valid = set(role for role in ctx.guild.roles if role.id in giveable_ids)
		
		already_have = valid & set(ctx.author.roles)
		given = valid - already_have
		await ctx.author.add_roles(*given)
		
		e = discord.Embed(color=discord.Color.blue())
		if given:
			given_names = sorted((role.name for role in given), key=str.casefold)
			e.add_field(name='Gave you {} role(s)!'.format(len(given)), value='\n'.join(given_names), inline=False)
		if already_have:
			already_have_names = sorted((role.name for role in already_have), key=str.casefold)
			e.add_field(name='You already have {} role(s)!'.format(len(already_have)), value='\n'.join(already_have_names), inline=False)
		extra = len(norm_names) - len(valid)
		if extra > 0:
			e.add_field(name='{} role(s) could not be found!'.format(extra), value='Use `{0.prefix}{0.invoked_with} list` to find valid giveable roles!'.format(ctx), inline=False)
		await ctx.send(embed=e)
	
	giveme.example_usage = """
	`{prefix}giveme Java` - gives you the role called Java, if it exists
	`{prefix}giveme Java, Python` - gives you the roles called Java and Python, if they exist
	"""
	
	@giveme.command()
	@bot_has_permissions(manage_roles=True)
	@has_permissions(manage_guild=True)
	async def add(self, ctx, *, name):
		"""Makes an existing role giveable, or creates one if it doesn't exist. Name must not contain commas.
		Similar to create, but will use an existing role if one exists."""
		if ',' in name:
			raise BadArgument('giveable role names must not contain commas!')
		norm_name = self.normalize(name)
		with db.Session() as session:
			settings = session.query(GuildSettings).filter_by(id=ctx.guild.id).one_or_none()
			if settings is None:
				settings = GuildSettings(id=ctx.guild.id)
				session.add(settings)
			if norm_name in (giveable.norm_name for giveable in settings.giveable_roles):
				raise BadArgument('that role already exists and is giveable!')
			candidates = [role for role in ctx.guild.roles if self.normalize(role.name) == norm_name]
			
			if not candidates:
				role = await ctx.guild.create_role(name=name, reason='Giveable role created by {}'.format(ctx.author))
			elif len(candidates) == 1:
				role = candidates[0]
			else:
				raise BadArgument('{} roles with that name exist!'.format(len(candidates)))
			settings.giveable_roles.append(GiveableRole.from_role(role))
		await ctx.send('Role "{0}" added! Use `{1}{2} {0}` to get it!'.format(role.name, ctx.prefix, ctx.command.parent))
	
	add.example_usage = """
	`{prefix}giveme add Java` - creates or finds a role named "Java" and makes it giveable
	`{prefix}giveme Java` - gives you the Java role that was just found or created
	"""
	
	@giveme.command()
	@bot_has_permissions(manage_roles=True)
	@has_permissions(manage_guild=True)
	async def create(self, ctx, *, name):
		"""Create a giveable role. Name must not contain commas.
		Similar to add, but will always create a new role."""
		if ',' in name:
			raise BadArgument('giveable role names must not contain commas!')
		norm_name = self.normalize(name)
		with db.Session() as session:
			settings = session.query(GuildSettings).filter_by(id=ctx.guild.id).one_or_none()
			if settings is None:
				settings = GuildSettings(id=ctx.guild.id)
				session.add(settings)
			if norm_name in (giveable.norm_name for giveable in settings.giveable_roles):
				raise BadArgument('that role already exists and is giveable!')
			
			role = await ctx.guild.create_role(name=name, reason='Giveable role created by {}'.format(ctx.author))
			settings.giveable_roles.append(GiveableRole.from_role(role))
		await ctx.send('Role "{0}" created! Use `{1}{2} {0}` to get it!'.format(role.name, ctx.prefix, ctx.command.parent))
	
	create.example_usage = """
	`{prefix}giveme create Python` - creates a role named "Python" and makes it giveable
	`{prefix}giveme Python` - gives you the Python role that was just created
	"""
	
	@giveme.command()
	@bot_has_permissions(manage_roles=True)
	async def remove(self, ctx, *, roles):
		"""Removes multiple giveable roles from you. Names must be separated by commas."""
		norm_names = [self.normalize(name) for name in roles.split(',')]
		with db.Session() as session:
			query = session.query(GiveableRole.id).filter(GiveableRole.guild_id == ctx.guild.id, GiveableRole.norm_name.in_(norm_names))
			removable_ids = [tup[0] for tup in query.all()]
			valid = set(role for role in ctx.guild.roles if role.id in removable_ids)
		
		removed = valid & set(ctx.author.roles)
		dont_have = valid - removed
		await ctx.author.remove_roles(*removed)
		
		e = discord.Embed(color=discord.Color.blue())
		if removed:
			removed_names = sorted((role.name for role in removed), key=str.casefold)
			e.add_field(name='Removed {} role(s)!'.format(len(removed)), value='\n'.join(removed_names), inline=False)
		if dont_have:
			dont_have_names = sorted((role.name for role in dont_have), key=str.casefold)
			e.add_field(name='You didn\'t have {} role(s)!'.format(len(dont_have)), value='\n'.join(dont_have_names), inline=False)
		extra = len(norm_names) - len(valid)
		if extra > 0:
			e.add_field(name='{} role(s) could not be found!'.format(extra), value='Use `{0.prefix}{0.invoked_with} list` to find valid giveable roles!'.format(ctx), inline=False)
		await ctx.send(embed=e)
	
	remove.example_usage = """
	`{prefix}giveme remove Java` - removes the role called "Java" from you (if it can be given with `{prefix}giveme`)
	`{prefix}giveme remove Java, Python` - removes the roles called "Java" and "Python" from you
	"""
	
	@giveme.command()
	@bot_has_permissions(manage_roles=True)
	@has_permissions(manage_guild=True)
	async def delete(self, ctx, *, name):
		"""Deletes and removes a giveable role."""
		if ',' in name:
			raise BadArgument('this command only works with single roles!')
		norm_name = self.normalize(name)
		valid_ids = set(role.id for role in ctx.guild.roles)
		with db.Session() as session:
			try:
				role = session.query(GiveableRole).filter(GiveableRole.guild_id == ctx.guild.id, GiveableRole.norm_name == norm_name, GiveableRole.id.in_(valid_ids)).one()
			except MultipleResultsFound:
				raise BadArgument('multiple giveable roles with that name exist!')
			except NoResultFound:
				raise BadArgument('that role does not exist or is not giveable!')
			else:
				session.delete(role)
		role = discord.utils.get(ctx.guild.roles, id=role.id) # Not null because we already checked for id in valid_ids
		await role.delete(reason='Giveable role deleted by {}'.format(ctx.author))
		await ctx.send('Role "{0}" deleted!'.format(role))
	
	delete.example_usage = """
	`{prefix}giveme delete Java` - deletes the role called "Java" if it's giveable (automatically removes it from all members)
	"""
	
	@cooldown(1, 10, BucketType.channel)
	@giveme.command(name='list')
	@bot_has_permissions(manage_roles=True)
	async def list_roles(self, ctx):
		"""Lists all giveable roles for this server."""
		with db.Session() as session:
			names = [tup[0] for tup in session.query(GiveableRole.name).filter_by(guild_id=ctx.guild.id)]
		e = discord.Embed(title='Roles available to self-assign', color=discord.Color.blue())
		e.description = '\n'.join(sorted(names, key=str.casefold))
		await ctx.send(embed=e)
	
	list_roles.example_usage = """
	`{prefix}giveme list` - lists all giveable roles
	"""
	
	@staticmethod
	def normalize(name):
		return name.strip().casefold()
	
	@command()
	@bot_has_permissions(manage_roles=True)
	@has_permissions(manage_roles=True)
	async def give(self, ctx, member : discord.Member, *, role : discord.Role):
		"""Gives a member a role. Not restricted to giveable roles."""
		if role > ctx.author.top_role:
			raise BadArgument('Cannot give roles higher than your top role!')
		await member.add_roles(role)
		await ctx.send('Successfully gave {} {}'.format(member, role))
	
	give.example_usage = """
	`{prefix}give cooldude#1234 Java` - gives cooldude any role, giveable or not, named Java
	"""
	
	@command()
	@bot_has_permissions(manage_roles=True)
	@has_permissions(manage_roles=True)
	async def take(self, ctx, member : discord.Member, *, role : discord.Role):
		"""Takes a role from a member. Not restricted to giveable roles."""
		if role > ctx.author.top_role:
			raise BadArgument('Cannot take roles higher than your top role!')
		await member.remove_roles(role)
		await ctx.send('Successfully removed "{}" from {}!'.format(role, member))
	
	take.example_usage = """
	`{prefix}take cooldude#1234 Java` - takes any role named Java, giveable or not, from cooldude
	"""

class GuildSettings(db.DatabaseObject):
	__tablename__ = 'guilds'
	id = db.Column(db.Integer, primary_key=True)
	giveable_roles = db.relationship('GiveableRole', back_populates='guild_settings')

class GiveableRole(db.DatabaseObject):
	__tablename__ = 'giveable_roles'
	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String(100), nullable=False)
	norm_name = db.Column(db.String(100), nullable=False)
	guild_id = db.Column(db.Integer, db.ForeignKey('guilds.id'))
	guild_settings = db.relationship('GuildSettings', back_populates='giveable_roles')
	
	@classmethod
	def from_role(cls, role):
		"""Creates a GiveableRole record from a discord.Role."""
		return cls(id=role.id, name=role.name, norm_name=Roles.normalize(role.name))

class MissingMember(db.DatabaseObject):
	__tablename__ = 'missing_members'
	guild_id = db.Column(db.Integer, primary_key=True)
	member_id = db.Column(db.Integer, primary_key=True)
	missing_roles = db.relationship('MissingRole', back_populates='member', cascade='all, delete, delete-orphan')

class MissingRole(db.DatabaseObject):
	__tablename__ = 'missing_roles'
	__table_args__ = (db.ForeignKeyConstraint(['guild_id', 'member_id'], ['missing_members.guild_id', 'missing_members.member_id']),)
	role_id = db.Column(db.Integer, primary_key=True)
	guild_id = db.Column(db.Integer) # Guild ID doesn't have to be primary because role IDs are unique across guilds
	member_id = db.Column(db.Integer, primary_key=True)
	role_name = db.Column(db.String(100), nullable=False)
	member = db.relationship('MissingMember', back_populates='missing_roles')

def setup(bot):
	bot.add_cog(Roles(bot))
