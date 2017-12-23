
from .. import db
from ._utils import *
import discord

# noinspection PyUnboundLocalVariable


class Teams(Cog):
	@command()
	async def setteam(self, ctx, team_type, team_number):
		team_type = team_type.casefold()
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

	@command()
	async def teamsfor(self, ctx, user: discord.Member=None):
		if user is None:
			user = ctx.author
		with db.Session() as session:
			users = session.query(TeamNumbers).filter_by(user_id=user.id).one_or_none()
			if users is None:
				await ctx.send("Couldn't find any teams for that user!")
			if users is not None:
				e = discord.Embed(type='rich')
				e.title = 'Teams for {}'.format(user.display_name)
				e.add_field(name="FRC Team", value=users.frc_team)
				e.add_field(name="FTC Team", value=users.ftc_team)
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
				for i in users:
					user = ctx.guild.get_member(i.user_id)
					e.add_field(name=user.display_name, value=user.mention, inline=False)
				await ctx.send(embed=e)


class TeamNumbers(db.DatabaseObject):
	__tablename__ = 'team_numbers'
	user_id = db.Column(db.Integer, primary_key=True)
	frc_team = db.Column(db.Integer)
	ftc_team = db.Column(db.Integer)


def setup(bot):
	bot.add_cog(Teams(bot))
