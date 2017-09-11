import discord
from discord.ext.commands import bot_has_permissions, BadArgument
from .. import db
from ._utils import *

class Roles(Cog):
	@group(invoke_without_command=True)
	@bot_has_permissions(manage_roles=True)
	async def giveme(self, ctx, *, roles):
		"""Give you one or more givable roles, separated by commas."""
		requests = set(name.strip().casefold() for name in roles.split(','))
		givables = self.givable_roles(ctx.guild)
		
		already_have = set(role for name, role in givables.items() if name in requests and role in ctx.author.roles)
		valid = set(role for name, role in givables.items() if name in requests and role not in already_have)
		
		await ctx.author.add_roles(*valid)
		
		e = discord.Embed(color=discord.Color.blue())
		if valid:
			e.add_field(name='Gave you {} role(s)!'.format(len(valid)), value='\n'.join(role.name for role in valid), inline=False)
		if already_have:
			e.add_field(name='You already have {} role(s)!'.format(len(already_have)), value='\n'.join(role.name for role in already_have), inline=False)
		extra = len(requests) - (len(already_have) + len(valid))
		if extra > 0:
			e.add_field(name='{} role(s) could not be found!'.format(extra), value='Use `{0.prefix}{0.invoked_with} list` to find valid givable roles!'.format(ctx), inline=False)
		await ctx.send(embed=e)
	
	@giveme.command()
	@bot_has_permissions(manage_roles=True)
	async def add(self, ctx, *, name):
		"""Makes an existing role givable, or creates one if it doesn't exist. Name must not contain commas.
		Similar to create, but will use an existing role if one exists."""
		if ',' in name:
			raise BadArgument('givable role names must not contain commas!')
		role = discord.utils.get(ctx.guild.roles, name=name)
		if role is None:
			role = await ctx.guild.create_role(name=name, reason='Givable role created by {}'.format(ctx.author))
		elif name.strip().casefold() in self.givable_roles(ctx.guild):
			raise BadArgument('that role already exists and is givable!')
		with db.Session() as session:
			givables = session.query(GivableRoles).filter_by(guild_id=ctx.guild.id).first()
			if givables is None:
				givables = GivableRoles(guild_id=ctx.guild.id, role_ids=str(role.id))
				session.add(givables)
			else:
				givables.role_ids += ' ' + str(role.id)
		await ctx.send('Created givable role {0}! Use `{1}{2} {0}` to get it!'.format(role, ctx.prefix, ctx.command.parent))
	
	@giveme.command()
	@bot_has_permissions(manage_roles=True)
	async def create(self, ctx, *, name):
		"""Create a givable role. Name must not contain commas.
		Similar to add, but will always create a new role."""
		if ',' in name:
			raise BadArgument('givable role names must not contain commas!')
		if name.strip().casefold() in self.givable_roles(ctx.guild):
			raise BadArgument('a duplicate role is givable and would conflict!')
		role = await ctx.guild.create_role(name=name, reason='Givable role created by {}'.format(ctx.author))
		with db.Session() as session:
			givables = session.query(GivableRoles).filter_by(guild_id=ctx.guild.id).first()
			if givables is None:
				givables = GivableRoles(guild_id=ctx.guild.id, role_ids=str(role.id))
				session.add(givables)
			else:
				givables.role_ids += ' ' + str(role.id)
		await ctx.send('Created givable role {0}! Use `{1}{2} {0}` to get it!'.format(role, ctx.prefix, ctx.command.parent))
	
	@staticmethod
	def givable_roles(guild):
		with db.Session() as session:
			roles = session.query(GivableRoles).filter_by(guild_id=guild.id).first()
		if roles is None:
			return {}
		givable_ids = [int(id_) for id_ in roles.role_ids.split(' ')]
		return {role.name.strip().casefold(): role for role in guild.roles if role.id in givable_ids}

class GivableRoles(db.DatabaseObject):
	__tablename__ = 'givable_roles'
	guild_id = db.Column(db.Integer, primary_key=True)
	role_ids = db.Column(db.String, nullable=True)

def setup(bot):
	bot.add_cog(Roles(bot))
