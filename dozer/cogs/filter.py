import asyncio
import discord
import re

from ._utils import *
from .. import db

class Filter(Cog):

	"""The filters need to be compiled each time they're run, but we don't want to compile every filter
	Every time it's run, or all of them at once when the bot starts. So the first time that filter is run,
	the compiled object is placed in here. This dict is actually a dict full of dicts, with each parent dict's key
	being the guild ID for easy accessing.
	"""
	filter_dict = {}

	"""From https://stackoverflow.com/questions/172303/is-there-a-regular-expression-to-detect-a-valid-regular-expression
	
	This can detect if a string is a regex pattern or simply a word. If this equates to false, the friendly name is also
	set to the pattern.
	"""
	regex_pattern = r"""
/
^                                             # start of string
(                                             # first group start
  (?:
    (?:[^?+*{}()[\]\\|]+                      # literals and ^, $
     | \\.                                    # escaped characters
     | \[ (?: \^?\\. | \^[^\\] | [^\\^] )     # character classes
          (?: [^\]\\]+ | \\. )* \]
     | \( (?:\?[:=!]|\?<[=!]|\?>)? (?1)?? \)  # parenthesis, with recursive content
     | \(\? (?:R|[+-]?\d+) \)                 # recursive matching
     )
    (?: (?:[?+*]|\{\d+(?:,\d*)?\}) [?+]? )?   # quantifiers
  | \|                                        # alternative
  )*                                          # repeat content
)                                             # end first group
$                                             # end of string
/"""

	"""Helper Functions"""

	def check_dm_filter(self, ctx):
		with db.Session() as session:
			results = session.query(WordFilterDMSetting).filter(WordFilterDMSetting.guild_id==ctx.guild.id)\
				.one_or_none()

			if results is None:
				results = True
			else:
				results = results.dm

			if results is True:
				if ctx.author.dm_channel is None:
					ctx.author.create_dm()
				return ctx.author.dm_channel
			else:
				return ctx.channel

	def load_filters(self, guild_id):
		with db.Session() as session:
			results = session.query(WordFilter).filter(WordFilter.guild_id==guild_id).all()
			self.filter_dict[guild_id] = {}
			for filter in results:
				self.filter_dict[guild_id][filter.id] = re.compile(filter.pattern)

	"""Event Handlers"""

	"""Commands"""
	@group(invoke_without_command=True)
	async def filter(self, ctx):
		with db.Session() as session:
			results = session.query(WordFilter).filter(WordFilter.guild_id==ctx.guild.id).all()
		if results == []:
			# TODO: Make this a embed
			await ctx.send("No filters found for this server. Use `{}filter add <>` to add one.".format(
				ctx.bot.command_prefix))
			return

		filter_text = ""
		for filter in results:
			filter_text += "ID {}: `{}`".format(filter.id, filter.friendly_name or filter.pattern)
			if results.index(filter) != (len(results)-1):
				filter_text += "\n"

		embed = discord.Embed()
		embed.title = title="Filters for {}".format(ctx.guild.name)
		embed.add_field(name="Filters", value=filter_text)
		channel = self.check_dm_filter(ctx)
		await channel.send(embed=embed)
		if isinstance(channel, discord.DMChannel):
			await ctx.message.add_reaction("📬")

	@filter.command()
	async def add(self, ctx, pattern, friendly_name=None):
		new_filter = WordFilter(guild_id=ctx.guild.id, pattern=pattern, friendly_name=friendly_name or None)
		with db.Session() as session:
			session.add(new_filter)
		self.load_filters(ctx.guild.id)
		embed = discord.Embed()
		embed.title = "Filter {} added".format(new_filter.id)
		embed.description = "A new filter with the name `{}` was added.".format(friendly_name or pattern)
		embed.add_field(name="Pattern", value="`{}`".format(pattern))
		await ctx.send(embed=embed)

	@filter.command()
	async def remove(self, ctx, id):
		with db.Session() as session:
			result = session.query(WordFilter).filter(WordFilter.id == id).one_or_none()
			if result is None:
				await ctx.send("Filter ID {} not found!".format(id))
				return
			if result.guild_id is not ctx.guild.id:
				await ctx.send("That Filter does not belong to this guild.")
				return
			session.delete(result)
			self.load_filters(ctx.guild.id)

	@filter.command(name="dm")
	async def dm_config(self, ctx, config: bool):
		with db.Session() as session:
			result = session.query(WordFilterDMSetting).filter(WordFilterDMSetting.guild_id == ctx.guild.id).one_or_none()
			before_setting = result.dm or None
			if result is None:
				dm_setting = WordFilterDMSetting(guild_id=ctx.guild.id, dm=config)
				session.add(dm_setting)
			else:
				result.dm = config
			await ctx.send("The DM setting for this guild has been changed from {} to {}.".format(before_setting, result.dm))

	@filter.group(invoke_without_command=True)
	async def whitelist(self, ctx):
		with db.Session() as session:
			results = session.query(WordFilterRoleWhitelist).filter(WordFilterRoleWhitelist.guild_id == ctx.guild.id).all()
			roles_text = ""
			for db_role in results:
				role = discord.utils.get(ctx.guild.roles, id=db_role.role_id)
				roles_text += "{}\n".format(role.name)
			embed = discord.Embed()
			embed.title = "Whitlisted roles for {}".format(ctx.guild.name)
			embed.description = "Anybody with any of the roles below will not have their messages filtered."
			embed.add_field(name="Roles",value=roles_text or "No roles")
			await ctx.send(embed=embed)

	@whitelist.command(name="add")
	async def whitelist_add(self, ctx, *, role: discord.Role):
		with db.Session() as session:
			result = session.query(WordFilterRoleWhitelist).filter(WordFilterRoleWhitelist.role_id == role.id).one_or_none()
			if result is not None:
				await ctx.send("That role is already whitelisted.")
			whitelist_entry = WordFilterRoleWhitelist(guild_id=ctx.guild.id, role_id=role.id)
			session.add(whitelist_entry)
			await ctx.send("Whitelisted `{}` for this guild.".format(role.name))

	@whitelist.command(name="remove")
	async def whitelist_remove(self, ctx, *, role:discord.Role):
		with db.Session() as session:
			result = session.query(WordFilterRoleWhitelist).filter(WordFilterRoleWhitelist.role_id == role.id).one_or_none()
			if result is None:
				await ctx.send("That role is not whitelisted.")
			session.delete(result)
			await ctx.send("The role `{}` is no longer whitelisted.".format(role.name))


def setup(bot):
	bot.add_cog(Filter(bot))


"""Database Tables"""


class WordFilter(db.DatabaseObject):
	__tablename__ = "word_filters"
	id = db.Column(db.Integer, primary_key=True)
	guild_id = db.Column(db.Integer)
	friendly_name = db.Column(db.String, nullable=True)
	pattern = db.Column(db.String)


class WordFilterDMSetting(db.DatabaseObject):
	__tablename__ = "word_filter_dm_setting"
	id = db.Column(db.Integer, primary_key=True)
	guild_id = db.Column(db.Integer)
	dm = db.Column(db.Boolean)


class WordFilterRoleWhitelist(db.DatabaseObject):
	__tablename__ = "word_filter_role_whitelist"
	id = db.Column(db.Integer, primary_key=True)
	guild_id = db.Column(db.Integer)
	role_id = db.Column(db.Integer)