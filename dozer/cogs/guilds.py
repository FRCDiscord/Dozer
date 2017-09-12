from ._utils import *
import discord
from discord.ext.commands import bot_has_permissions, has_permissions, BadArgument
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm.exc import NoResultFound
from .. import db


class Guilds(Cog):
	@group(invoke_without_command=True)
	async def guilds(self, ctx):
		e = discord.Embed()
		e.title = "All the channels {0.name} is on.".format(await self.bot.application_info())
		for guild in db.Session().query(Guild).limit(25):
			e.add_field(name=guild.name)
		await ctx.send(embed=e)

	@guilds.command()
	@bot_has_permissions(manage_roles=True)
	@has_permissions(manage_guild=True)
	async def edit(self,ctx):
		pass

	async def on_ready(self):
		for guild in self.bot.guilds:
			try:
				db.Session().query(Guild).filter(Guild.id == guild.id).one()
			except NoResultFound:
				guilddb = Guild
				guilddb.id = guild.id
				guilddb.name = guild.name
				guilddb.invite = None
				if guild.owner.dm_channel is None:
					await guild.owner.create_dm()
				await guild.owner.dm_channel.send("Your guild {0} was just added to Dozer's database of ever-growing\
				 FIRST server. Use `{1}guilds settings` to change your tags and information about this server to show\
				 to other users.".format(guild.name, self.bot.command_prefix))
				db.Session().add(guilddb)
		db.Session().commit()



	def __init__(self, bot):
		super().__init__(bot)
		bot.add_listener(self.on_ready)

class GuildRelation(db.DatabaseObject):
	__tablename__ = 'guild_relations'

	id = Column(Integer, primary_key=True)
	cat_type = Column(String)  # Specify if region, district, interest, etc
	cat_ = Column(String)  # Specify which region, dist, etc
	description = Column(String)

class Guild(db.DatabaseObject):
	__tablename__ = 'guilds'

	id = Column(Integer, primary_key=True)
	name = Column(String)
	prefix = Column(String)
	invite = Column(String, nullable=True)
	desc = Column(String)

def setup(bot):
	bot.add_cog(Guilds(bot))
