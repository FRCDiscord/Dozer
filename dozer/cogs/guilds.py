from ._utils import *
from sqlalchemy import Column, Integer, String


class Guilds(Cog):

	class GuildRelation(Cog.bot.base):
		__tablename__ = 'guild_relations'

		id = Column(Integer, primary_key=True)
		relation_type = Column(String)  # Specify if region, district, interest, etc
		relation_info = Column(String)  # Specify which region, dist, etc
		description = Column(String)


def setup(bot):
	bot.add_cog(Guilds(bot))
