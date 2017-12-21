
from .. import db
from ._utils import *
from discord.ext.commands import BadArgument


# noinspection PyUnboundLocalVariable
class Teams(Cog):
	@command()
	async def setteam(self, ctx, team_number, team_type):
		with db.Session() as session:
			user = session.query(TeamNumbers).filter_by(user_id=ctx.author.id).one_or_none()
			if user is not None:
				user.user_id = ctx.author.id
				if team_type == "frc":
					user.frc_team = team_number
				elif team_type == "ftc":
					user.ftc_team = team_number
			if user is None:
				if team_type == "frc":
					dbtransaction = TeamNumbers(user_id=ctx.author.id, frc_team=int(team_number))
				elif team_type == "ftc":
					dbtransaction = TeamNumbers(user_id=ctx.author.id, frc_team=int(team_number))
				session.add(dbtransaction)
		await ctx.send("Team number set!")


class TeamNumbers(db.DatabaseObject):
	__tablename__ = 'team_numbers'
	user_id = db.Column(db.Integer, primary_key=True)
	frc_team = db.Column(db.Integer)
	ftc_team = db.Column(db.Integer)


def setup(bot):
	bot.add_cog(Teams(bot))
