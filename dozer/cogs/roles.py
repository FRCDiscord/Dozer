import discord
from discord.ext.commands import bot_has_permissions
from .. import db
from ._utils import *

class Roles(Cog):
	@group(invoke_without_command=True)
	@bot_has_permissions(manage_roles=True)
	async def giveme(self, ctx):
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
