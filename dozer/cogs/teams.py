
from .. import db
from ._utils import *
import discord
from discord.ext.commands import BadArgument, bot_has_permissions


class Teams(Cog):
	@command()
	async def setteam(self, ctx, team_type, team_number):
		"""Sets an association with your team in the database."""
		team_type = team_type.casefold()
		with db.Session() as session:
			dbtransaction = TeamNumbers(user_id=ctx.author.id, team_number=int(team_number), team_type=team_type)
			session.add(dbtransaction)
		await ctx.send("Team number set!")
	setteam.example_usage = """
	`{prefix}setteam type team_number` - Creates an association in the database with a specified team
	"""

	@bot_has_permissions(manage_nick=True)
	async def on_member_join(self, member):
		with db.Session as session:
			query = session.query(TeamNumbers).filter_by(user_id=member.id).all()
			if len(query) == 0:
				print("Debugging: no team found in DB")
			elif len(query) == 1:
				member.edit(nick="{} {}".format(member.nick, query.team_number))
				print("Debugging: 1 team found in DB")
			elif len(query) > 1:
				print("Debugging: more than one team association found")

	@command()
	async def removeteam(self, ctx, team_type, team_number):
		"""Removes an association with a team in the database."""
		team_type = team_type.casefold()
		with db.Session() as session:
			results = session.query(TeamNumbers).filter_by(user_id=ctx.author.id, team_type=team_type, team_number=team_number).one_or_none()
			if results is not None:
				session.delete(results)
				await ctx.send("Removed association with {} team {}".format(team_type, team_number))
			if results is None:
				await ctx.send("Couldn't find any associations with that team!")
	removeteam.example_usage = """
	`{prefix}removeteam type team_number` - Removes your associations with a specified team 
	"""

	@command()
	async def teamsfor(self, ctx, user: discord.Member=None):
		"""Allows you to see the teams for the mentioned user. If no user is mentioned, your teams are displayed."""
		if user is None:
			user = ctx.author
		with db.Session() as session:
			teams = session.query(TeamNumbers).filter_by(user_id=user.id).order_by("team_type desc", "team_number asc").all()
			if len(teams) is 0:
				raise BadArgument("Couldn't find any team associations for that user!")
			else:
				e = discord.Embed(type='rich')
				e.title = 'Teams for {}'.format(user.display_name)
				e.description = "Teams: \n"
				for i in teams:
					e.description = "{} {} Team {} \n".format(e.description, i.team_type.upper(), i.team_number)
				await ctx.send(embed=e)
	teamsfor.example_usage = """
	`{prefix}teamsfor member` - Returns all team associations with the mentioned user. Assumes caller if blank.
	"""

	@command()
	async def onteam(self, ctx, team_type, team_number):
		"""Allows you to see who has associated themselves with a particular team."""
		team_type = team_type.casefold()
		with db.Session() as session:
			users = session.query(TeamNumbers).filter_by(team_number=team_number, team_type=team_type).all()
			if len(users) == 0:
				await ctx.send("Nobody on that team found!")
			else:
				e = discord.Embed(type='rich')
				e.title = 'Users on team {}'.format(team_number)
				e.description = "Users: \n"
				for i in users:
					user = ctx.guild.get_member(i.user_id)
					if user is not None:
						e.description = "{}{} {} \n".format(e.description, user.display_name, user.mention)
				await ctx.send(embed=e)
	onteam.example_usage = """
	`{prefix}onteam type team_number` - Returns a list of users associated with a given team type and number
	"""


class TeamNumbers(db.DatabaseObject):
	__tablename__ = 'team_numbers'
	user_id = db.Column(db.Integer, primary_key=True)
	team_number = db.Column(db.Integer, primary_key=True)
	team_type = db.Column(db.String, primary_key=True)


def setup(bot):
	bot.add_cog(Teams(bot))
