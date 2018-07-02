import asyncio
import discord
import re

from ._utils import *
from .. import db

class Filter(Cog):

	"""The filters need to be compiled each time they're run, but we don't want to compile every filter
	Every time it's run, or all of them at once when the bot starts. So the first time that filter is run,
	the compiled object is placed in here.
	"""
	filter_dict = {}

	"""From https://stackoverflow.com/questions/172303/is-there-a-regular-expression-to-detect-a-valid-regular-expression
	
	This can detect if a string is a regex pattern or simply a word. If this equates to false, the friendly name is also
	set to the pattern.
	"""
	regex_pattern = r"/^((?:(?:[^?+*{}()[\]\\|]+|\\.|\[(?:\^?\\.|\^[^\\]|[^\\^])(?:[^\]\\]+|\\.)*\]|\((?:\?[:=!]|\?<[=!]|\?>)?(?1)??\)|\(\?(?:R|[+-]?\d+)\))(?:(?:[?+*]|\{\d+(?:,\d*)?\})[?+]?)?|\|)*)$/"

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

	"""Event Handlers"""


	"""Commands"""
	@group(invoke_without_command=True)
	async def filter(self, ctx):
		with db.Session() as session:
			results = session.query(WordFilter).filter(WordFilter.guild_id==ctx.guild.id).all()
		if results == []:
			#TODO: Make this a embed
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
		self.filter_dict[new_filter.id] = re.compile(pattern)
		embed = discord.Embed()
		embed.title = "Filter {} added".format(new_filter.id)
		embed.description = "A new filter with the name `{}` was added.".format(friendly_name or pattern)
		embed.add_field(name="Pattern", value="`{}`".format(pattern))
		await ctx.send(embed=embed)

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
	role_id = db.Column(db.Integer)