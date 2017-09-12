import discord, discord.utils
from discord.ext.commands import bot_has_permissions, has_permissions, BadArgument
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
			settings = session.query(GuildSettings).one_or_none()
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
			settings = session.query(GuildSettings).one_or_none()
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
		"""[DISABLED] Removes multiple giveable roles from you. Names must be separated by commas."""
	
	@giveme.command()
	@bot_has_permissions(manage_roles=True)
	@has_permissions(manage_guild=True)
	async def delete(self, ctx, *, name):
		"""[DISABLED] Deletes and removes a giveable role."""
	
	@giveme.command(name='list')
	@bot_has_permissions(manage_roles=True)
	async def list_roles(self, ctx):
		"""[DISABLED] Lists all giveable roles for this server."""
	
	@staticmethod
	def normalize(name):
		return name.strip().casefold()

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
