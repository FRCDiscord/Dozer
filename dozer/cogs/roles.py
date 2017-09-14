import discord, discord.utils
from discord.ext.commands import bot_has_permissions, has_permissions, BadArgument
from sqlalchemy.orm.exc import MultipleResultsFound, NoResultFound
from .. import db
from ._utils import *

class Roles(Cog):
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
	
	@giveme.command(name='list')
	@bot_has_permissions(manage_roles=True)
	async def list_roles(self, ctx):
		"""Lists all giveable roles for this server."""
		with db.Session() as session:
			names = [tup[0] for tup in session.query(GiveableRole.name).filter_by(guild_id=ctx.guild.id)]
		e = discord.Embed(title='Roles available to self-assign', color=discord.Color.blue())
		e.description = '\n'.join(sorted(names, key=str.casefold))
		await ctx.send(embed=e)
	
	@staticmethod
	def normalize(name):
		return name.strip().casefold()
	
	@command()
	@bot_has_permissions(manage_roles=True)
	@has_permissions(manage_roles=True)
	async def give(self, ctx, member : discord.Member, *, role : discord.Role):
		"""Gives a member a role. Not restricted to giveable roles."""
		await member.add_roles(role)
		await ctx.send('Successfully gave {} "{}"!'.format(member, role))
	
	@command()
	@bot_has_permissions(manage_roles=True)
	@has_permissions(manage_roles=True)
	async def take(self, ctx, member : discord.Member, *, role : discord.Role):
		await member.remove_roles(role)
		await ctx.send('Successfully removed "{}" from {}!'.format(role, member))

class GuildSettings(db.DatabaseObject):
	__tablename__ = 'guilds'
	id = db.Column(db.Integer, primary_key=True)

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

GuildSettings.giveable_roles = db.relationship('GiveableRole', order_by=GiveableRole.id, back_populates='guild_settings')

def setup(bot):
	bot.add_cog(Roles(bot))
