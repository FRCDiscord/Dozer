
from .. import db
from ._utils import *
import discord

# noinspection PyUnboundLocalVariable


class Teams(Cog):
	@command()
	async def setteam(self, ctx, team_type, team_number):
		team_type = team_type.casefold()
		with db.Session() as session:
			if team_type == "frc":
				dbtransaction = TeamNumbers(user_id=ctx.author.id, frc_team=int(team_number))
			elif team_type == "ftc":
				dbtransaction = TeamNumbers(user_id=ctx.author.id, ftc_team=int(team_number))
			else:
				dbtransaction = None
				await ctx.send("Invalid team type!")
			session.add(dbtransaction)
		await ctx.send("Team number set!")

	@command()
	async def removeteam(self, ctx, team_type, team_number):
		team_type = team_type.casefold()
		with db.Session() as session:
			counter = 0
			if team_type == 'frc':
				results = session.query(TeamNumbers).filter_by(user_id=ctx.author.id, frc_team=team_number).all()
			elif team_type == 'ftc':
				results = session.query(TeamNumbers).filter_by(user_id=ctx.author.id, ftc_team=team_number).all()
			else:
				results = {}
				await ctx.send("Please specify a valid team type!")
			for i in results:
				session.delete(i)
				counter += 1
			await ctx.send("Removed {} associations with team {}".format(counter, team_number))

	@command()
	async def teamsfor(self, ctx, user: discord.Member=None):
		if user is None:
			user = ctx.author
		with db.Session() as session:
			teams = session.query(TeamNumbers).filter_by(user_id=user.id).all()
			if len(teams) is 0:
				await ctx.send("Couldn't find any teams for that user!")
			else:
				e = discord.Embed(type='rich')
				e.title = 'Teams for {}'.format(user.display_name)
				e.description = "Teams: \n"
				for i in teams:
					if i.frc_team is not None:
						e.description = "{} FRC Team {} \n".format(e.description, i.frc_team)
					if i.ftc_team is not None:
						e.description = "{} FTC Team {} \n".format(e.description, i.ftc_team)
				await ctx.send(embed=e)

	@command()
	async def onteam(self, ctx, team_type, team_number):
		team_type = team_type.casefold()
		with db.Session() as session:
			badteamtype = False
			if team_type == 'frc':
				users = session.query(TeamNumbers).filter_by(frc_team=team_number).all()
			elif team_type == 'ftc':
				users = session.query(TeamNumbers).filter_by(ftc_team=team_number).all()
			else:
				await ctx.send("Please specify a valid team type!")
				users = []
				badteamtype = True
			if len(users) <= 0:
				if not badteamtype:
					await ctx.send("Nobody on that team found!")
			else:
				e = discord.Embed(type='rich')
				e.title = 'Users on team {}'.format(team_number)
				e.description = "Users: \n"
				for i in users:
					user = ctx.guild.get_member(i.user_id)
					e.description = "{}{} {} \n".format(e.description, user.display_name, user.mention)
				await ctx.send(embed=e)


class TeamNumbers(db.DatabaseObject):
	__tablename__ = 'team_numbers'
	user_id = db.Column(db.Integer)
	frc_team = db.Column(db.Integer)
	ftc_team = db.Column(db.Integer)
	primary_key = db.Column(db.Integer, primary_key=True, autoincrement=True)


def setup(bot):
	bot.add_cog(Teams(bot))
