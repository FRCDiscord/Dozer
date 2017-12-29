import discord
import datetime
import pickle
import lzma
import asyncio
import tbapi
import traceback
from ._utils import *
from .. import db
from discord.ext import commands
from discord.ext.commands import BadArgument, Group, bot_has_permissions, has_permissions
from datetime import timedelta
from collections import OrderedDict
from fuzzywuzzy import fuzz
from functools import wraps

SUPPORTED_MODES = ["frc", "ftc"]
def keep_alive(func):
	# keeps the wrapped async function alive; functions must have self and ctx as args
	@wraps(func)
	async def wrapper(self, ctx, *args, **kwargs):
		while True:
			try:
				return await func(self, ctx, *args, **kwargs)
			except Exception as e:
				# CancelledErrors are normal part of operation, ignore them
				if isinstance(e, asyncio.CancelledError):
					return
				# panic to the console, and to chat
				error = traceback.format_exc()
				print(error)
				await ctx.send(f"```Error in game loop:\n{error[:1974]}```")
	return wrapper

def game_is_running(func):
	@wraps(func)
	async def wrapper(*args, **kwargs):
		self = args[0]
		ctx = args[1]
		if ctx.channel.id not in self.games:
			await ctx.send(f"There's not a game going on! Start one with `{ctx.prefix}ng startround`")
			return

		return await func(*args, **kwargs)
	return wrapper

class NameGameSession():
	def __init__(self, mode):
		self.running = True
		self.players = OrderedDict()
		self.removed_players = []
		self.picked = []
		self.mode = mode
		self.time = 60
		self.vote_time = -1
		self.number = 0
		self._idx = 0
		self.last_name = ""
		self.last_team = 0
		self.state_lock = None
		self.turn_msg = None
		self.turn_embed = None
		self.turn_task = None

		self.pass_tally = 0
		self.fail_tally = 0
		
		self.vote_correct = False
		self.vote_player = None
		self.vote_msg = None
		self.vote_embed = None
		self.vote_task = None

	def create_embed(self, title="", description="", color=discord.Color.blurple(), extra_fields=[], start=False):
		v = "Starting " if start else "Current "
		embed = discord.Embed()
		embed.title = title
		embed.description = description
		embed.color = color
		embed.add_field(name="Players", value=", ".join([p.display_name for p in self.players.keys()]) or "n/a")
		embed.add_field(name=v+"Player", value=self.current_turn())
		embed.add_field(name=v+"Number", value=self.number or "Wildcard")
		embed.add_field(name="Time Left", value=self.time)

		for name, value in extra_fields:
			embed.add_field(name=name, value=value)
		return embed

	def check_name(self, ctx, team, name):
		tba_parser = ctx.cog.tba_parser
		ftc_teams = ctx.cog.ftc_teams

		actual_name = ""

		if self.mode == "frc":
			# check for existence
			try:
				team_data = tba_parser.get_team(f"frc{team}")
			except KeyError:
				return -1
			actual_name = team_data.nickname
		elif self.mode == "ftc":
			if team not in ftc_teams:
				return -1
			actual_name = ftc_teams[team]

		self.last_name = actual_name
		self.last_team = team
		return fuzz.partial_ratio(actual_name.lower(), name.lower())

	def current_turn(self):
		return list(self.players.keys())[self._idx]

	def next_turn(self):
		self.pass_tally = 0
		self.fail_tally = 0
		self.time = 60
		self._idx = (self._idx + 1) % len(self.players)

	def strike(self, player):
		self.players[player] += 1
		if self.players[player] >= 3:
			self.removed_players.append(player)
			self.players.pop(player)
			return True
		return False

	def check_win(self):
		return len(self.players) == 1

	def get_picked(self):
		return ", ".join(map(str, sorted(self.picked))) or "No Picked Teams"


class NameGame(Cog):
	def __init__(self, bot):
		super().__init__(bot)
		with lzma.open("ftc_teams.pickle.xz") as f:
			raw_teams = pickle.load(f)
			self.ftc_teams = {team: data['seasons'][0]['name'] for (team, data) in raw_teams.items()}
		self.games = {}

		tba_config = bot.config['tba']
		self.tba_parser = tbapi.TBAParser(tba_config['team'], tba_config['application'], tba_config['version'])

	
	@group(invoke_without_command=True)
	async def ng(self, ctx):
		"""Show info about and participate in a robotics team namegame.
		Run the help command on each of the subcommands for more detailed help.
		List of subcommands:
			ng info
			ng startround
			ng addplayer
			ng pick
			ng drop
			ng skip
			ng gameinfo
		"""
		await self.info.callback(self, ctx)
	
	ng.example_usage = """
	`{prefix}ng` - show a description on how the robotics team namegame works. 
	"""
	
	@ng.command()
	@bot_has_permissions(embed_links=True)
	async def info(self, ctx):
		"""Show a description of the robotics team name game and how to play."""
		game_embed = discord.Embed()
		game_embed.color = discord.Color.magenta()
		game_embed.title="How to play"
		game_embed.description = "This is a very simple little game where players will name a team number and name that starts with the last digit of the last named team. Some more specific rules are below:"
		game_embed.add_field(name="No Double Picking", value="Only pick teams once.")
		game_embed.add_field(name="Three Strikes, You're Out!",value="You are only allowed three strikes, which are given by picking out of turn, getting the team name wrong, picking a non existant team, being voted that your pick is incorrect, not picking in time, or picking a already picked team.")
		game_embed.add_field(name="No Cheatsy Doodles",value="No looking up teams on TBA, TOA, VexDB, or other methods, that's just unfair.")
		game_embed.add_field(name="Times up!", value="You have 60 seconds to make a pick, or you get skipped and get a strike.")
		game_embed.add_field(name="Shaking Things Up",value="Any team number that ends in a 0 mean that the next player has a wildcard, and can pick any legal team.")
		game_embed.add_field(name="Pesky Commands", value=f"To start a game, type `{ctx.prefix}ng startround` and mention the players you want to play with. \
				You can add people with `{ctx.prefix}ng addplayer`. \
				When it's your turn, type `{ctx.prefix}ng pick <team> <teamname>` to execute your pick. \
				If you need to skip, typing `{ctx.prefix}ng skip` gives you a strike and skips your turn. \
				You can always do `{ctx.prefix}ng gameinfo` to get the current game status. \
				If you ever need to quit, running `{ctx.prefix}ng drop` removes you from the game. \
				For more detailed command help, run `{ctx.prefix}help ng.")
		game_embed.add_field(name="Different Game Modes", value="You can play the name game with FTC teams too! To start a game playing with FTC teams, run `{ctx.prefix}ng startround ftc`")
		await ctx.send(embed=game_embed)

	info.example_usage = """
	`{prefix}ng help` - show a description on how the robotics team namegame works
	"""
	
	@ng.group(invoke_without_command=True)
	async def config(self, ctx):
		await ctx.send(f"""`{ctx.prefix}ng config` reference:
				`{ctx.prefix}ng config defaultmode [mode]` - set tbe default game mode used when startround is used with no arguments
				`{ctx.prefix}ng config setchannel [channel_mention]` - set the channel that games are allowed to be run in
				`{ctx.prefix}ng config clearsetchannel` - clear the set channel for games""")
	@config.command()	
	@has_permissions(manage_guild=True)
	async def defaultmode(self, ctx, mode : str = None):
		with db.Session() as session:
			config = session.query(NameGameDefaultMode).filter_by(guild_id=ctx.guild.id).one_or_none()
			if mode is None:
				mode = SUPPORTED_MODES[0] if config is None else config.mode
				await ctx.send(f"The current default game mode for this server is `{mode}`")
			else:
				if mode not in SUPPORTED_MODES:
					await ctx.send(f"Game mode `{mode}` not supported! Please pick a mode that is one of: `{', '.join(SUPPORTED_MODES)}`")
					return
				if config is None:
					config = NameGameDefaultMode(guild_id=ctx.guild.id, mode=mode)
					session.add(config)
				else:
					config.mode = mode
				await ctx.send(f"Default game mode updated to `{mode}`")
	@config.command()
	@has_permissions(manage_guild=True)
	async def setchannel(self, ctx, channel : discord.TextChannel = None):
		with db.Session() as session:
			config = session.query(NameGameChannel).filter_by(guild_id=ctx.guild.id).one_or_none()
			if channel is None:
				if config is None or config.channel_id is None:
					await ctx.send(f"There is no currently set namegame channel.\nTo set a channel, run `{ctx.prefix}ng config setchannel [channel_mention]`")
				else:
					await ctx.send(f"The currently set namegame channel is {ctx.guild.get_channel(config.channel_id).mention}.\nTo clear this, run `{ctx.prefix}ng config clearsetchannel`")
			else:
				if config is None:
					config = NameGameChannel(guild_id=ctx.guild.id, channel_id=channel.id)
					session.add(config)
				else:
					config.channel_id = channel.id
				await ctx.send(f"Namegame channel set to {channel.mention}!")
	@config.command()
	@has_permissions(manage_guild=True)
	async def clearsetchannel(self, ctx):
		with db.Session() as session:
			config = session.query(NameGameChannel).filter_by(guild_id=ctx.guild.id).one_or_none()
			if config is not None:
				config.channel_id = None
			await ctx.send("Namegame channel cleared!")

	#TODO: configurable time limits, ping on event, etc

	@ng.command()
	async def startround(self, ctx, mode : str = None):
		"""
		Starts a namegame session.
		One can select the robotics program by specifying one of "FRC" or "FTC".
		"""
		if mode is None:
			with db.Session() as session:
				config = session.query(NameGameDefaultMode).filter_by(guild_id=ctx.guild.id).one_or_none()
			mode = SUPPORTED_MODES[0] if config is None else config.mode

		with db.Session() as session:
			config = session.query(NameGameChannel).filter_by(guild_id=ctx.guild.id).one_or_none()
			if config is not None and config.channel_id is not None and config.channel_id != ctx.channel.id:
				await ctx.send("Games cannot be started in this channel!")
				return

		if ctx.channel.id in self.games:
			await ctx.send("A game is currently going on! Wait till the players finish up to start again.")
			return
		if mode.lower() not in SUPPORTED_MODES:
			await ctx.send(f"Game mode `{mode}` not supported! Please pick a mode that is one of: `{', '.join(SUPPORTED_MODES)}`")
			return
		game = NameGameSession(mode.lower())
		game.state_lock = asyncio.Lock(loop=self.bot.loop)
		game.players[ctx.author] = 0
		for player in ctx.message.mentions:
			if player == ctx.author: 
				continue
			if player.bot:
				await ctx.send(f"You can't invite bot users like {player.mention}!")
				continue
			game.players[player] = 0
		await self.send_turn_embed(ctx, game,
			title=f"{mode.upper()} Name Game", 
			description="A game has been started! The info about the game is as follows:", 
			color=discord.Color.green()
		)
		#await ctx.send(f"{game.current_turn().mention}, start us off!")
		self.games[ctx.channel.id] = game	
		#game.event_loop = self.bot.loop.create_task(self.game_timer_loop(ctx, game))
		game.turn_task = self.bot.loop.create_task(self.game_turn_countdown(ctx, game))
	startround.example_usage = """
	`{prefix}ng startround frc` - start an FRC namegame session.
	"""

	@ng.command()
	@game_is_running
	async def addplayer(self, ctx):
		"""Add players to the current game.
		Only works if the user is currently playing."""
		if ctx.channel.id not in self.games:
			await ctx.send(f"There's not a game going on! Start one with `{ctx.prefix}ng startround`")
			return
		game = self.games[ctx.channel.id]

		with await game.state_lock:
			added = False
			for player in ctx.message.mentions:
				if player.bot:
					await ctx.send(f"You can't invite bot users like {player.mention}!")
					continue

				if player in game.removed_players:
					await ctx.send(f"{player.mention} is already out of the game and can't be added back in.")
				elif player in game.players:
					await ctx.send(f"{player.mention} is already in the game!")
				game.players[player] = 0
				added = True

			if not added: return
			await ctx.send(embed=game.create_embed(
				title="Players have been added to the game.",
				description="See below for an updated player list.", 
				color=discord.Color.blurple()
			))
	addplayer.example_usage = """
	`{prefix}ng addplayer @user1, @user2` - add user1 and user2 to the game.
	"""

	@ng.command()
	@game_is_running
	async def pick(self, ctx, team : int, *, name):
		"""Attempt to pick a team in a game."""
		game = self.games[ctx.channel.id]

		with await game.state_lock:
			if ctx.author != game.current_turn():
				if ctx.author in game.players:
					await ctx.send("It's not your turn! You've been given a strike for this behaviour! Don't let it happen again...")
					await self.strike(ctx, game, ctx.author)
				else:
					await ctx.send(f"Let the people playing play! If you want to join, ask one of the people currently playing to run `{ctx.prefix}ng addplayer {ctx.author.display_name}`")
				return

			if game.time < 0:
				await ctx.send("Vote on the current team before picking the next!")
				return

			if game.number != 0 and str(game.number) != str(team)[0]:
				await self.skip_player(ctx, game, ctx.author, "Your team doesn't start with the correct digit! Strike given, moving onto the next player!")
				return
			if team in game.picked:
				await self.skip_player(ctx, game, ctx.author, "That team has already been picked! You have been skipped and given a strike.")
				return

			ratio = game.check_name(ctx, team, name)
			if ratio == -1:
				#nonexistant team
				await self.skip_player(ctx, game, ctx.author, f"Team {team} doesn't exist! Strike given, moving onto the next player!")
				return
			if ratio > 60:
				game.picked.append(team)
				game.number = game.last_team % 10
				game.next_turn()
				game.vote_correct = True
				game.vote_time = 20
				game.vote_player = ctx.author
				await self.send_turn_embed(ctx, game,
					title="Team correct!",
					description=f"Team {team} ({game.last_name}) was {ratio}% correct! Moving onto the next player as follows. Click the red X to override this decision.",
					color=discord.Color.green(),
					extra_fields=[("Voting Time", game.vote_time)]
				)
				await game.turn_msg.add_reaction('❌')
				game.vote_msg = game.turn_msg
				game.vote_embed = game.turn_embed

				# EXTREMELY INCOMPLETE LOL
				# (not anymore)
			else:
				game.time = -1
				game.vote_time = 60
				game.vote_player = ctx.author
				game.vote_correct = False
				vote_embed = discord.Embed()
				vote_embed.color = discord.Color.gold()
				vote_embed.title = "A vote is needed!"
				vote_embed.description = "A player has made a choice with less than 50% similarity. The details of the pick are below. Click on the two emoji to vote if this is correct or not. A 50% majority of players is required to accept it, otherwise the player will get a strike."
				vote_embed.add_field(name="Player", value=game.current_turn().mention)
				vote_embed.add_field(name="Team", value=team)
				vote_embed.add_field(name="Said Name", value=name)
				vote_embed.add_field(name="Actual Name", value=game.last_name)
				vote_embed.add_field(name="Similarity", value=f"{ratio}%")
				vote_embed.add_field(name="Voting Time", value=game.vote_time)
				game.vote_embed = vote_embed
				game.vote_msg = await ctx.send(embed=vote_embed)
				await game.vote_msg.add_reaction('✅')
				await game.vote_msg.add_reaction('❌')
				game.vote_task = self.bot.loop.create_task(self.game_vote_countdown(ctx, game))


	pick.example_usage = """
	`{prefix}ng pick 254 poofy cheeses` - attempt to guess team 254 with a specified name of "poofy cheeses".
	"""
	@ng.command()
	@game_is_running
	async def drop(self, ctx):
		"""Drops a player from the current game by eliminating them. Once dropped, they can no longer rejoin."""
		game = self.games[ctx.channel.id]
		with await game.state_lock:
			if ctx.author not in game.players:
				await ctx.send("You can't leave a game you're not in!")
				return
			game.players[ctx.author] = 2
			if ctx.author == game.current_turn():
				await self.skip_player(ctx, game, ctx.author)
			else:
				await self.strike(ctx, game, ctx.author)
			if game.running:
				await self.display_info(ctx, game)
	drop.example_usage = """
	`{prefix}ng drop` - remove the initiator of the command from the current game
	"""
	@ng.command()
	@game_is_running
	async def skip(self, ctx):
		"""Skips the current player if the player wishes to forfeit their turn."""
		game = self.games[ctx.channel.id]
		with await game.state_lock:
			if ctx.author != game.current_turn():
				await ctx.send("It's not your turn! Only the current player can skip their turn!")
			else:
				await self.skip_player(ctx, game, ctx.author)
	skip.example_usage = """
	`{prefix}ng skip` - skip the current player's turn
	"""

	@ng.command()
	@game_is_running
	async def gameinfo(self, ctx):
		"""Display info about the currently running game."""
		game = self.games[ctx.channel.id]
		await self.display_info(ctx, game)

	gameinfo.example_usage = """
	`{prefix}ng gameinfo` - display info about the currently running game.
	"""
	

	async def strike(self, ctx, game, player):
		if game.strike(player):
			await ctx.send(f"Player {player.mention} is ELIMINATED!")
		if len(game.players) == 0:
			await ctx.send("Game disbanded, no winner called!")
			game.running = False
		if game.check_win():
			# winning condition
			winner = list(game.players.keys())[0]
			with db.Session() as session:
				record = session.query(NameGameLeaderboard).filter_by(user_id=winner.id, game_mode=game.mode).one_or_none()
				if record is None:
					record = NameGameLeaderboard(user_id=winner.id, wins=1, game_mode=game.mode)
					session.add(record)
				else:
					record.wins += 1
			win_embed = discord.Embed()
			win_embed.color = discord.Color.gold()
			win_embed.title = "We have a winner!"
			win_embed.add_field(name="Winning Player", value=winner)
			win_embed.add_field(name="Wins Total", value=record.wins)
			win_embed.add_field(name="Teams Picked", value=game.get_picked())
			await ctx.send(embed=win_embed)

			game.running = False

		if not game.running:
			self.games.pop(ctx.channel.id)
	
	async def display_info(self, ctx, game):
		info_embed = discord.Embed(title="Current Game Info", color=discord.Color.blue())
		info_embed.add_field(name="Game Type", value=game.mode.upper())
		info_embed.add_field(
				name="Strikes",
				value="\n".join([f"{player.display_name}: {strikes}" for player, strikes in game.players.items()])
		)
		info_embed.add_field(name="Current Player", value=game.current_turn())
		info_embed.add_field(name="Current Number", value=game.number or "Wildcard")
		info_embed.add_field(name="Time Left", value=game.time)
		info_embed.add_field(name="Teams Picked", value=game.get_picked())
		await ctx.send(embed=info_embed)

	async def skip_player(self, ctx, game, player, msg=None):
		if msg is not None:
			await ctx.send(msg)
		game.next_turn()
		await self.send_turn_embed(ctx, game,
			title=f"Player {player.display_name} was skipped and now has {game.players[player]+1} strike(s)!",
			color=discord.Color.red()
		)
		await self.strike(ctx, game, player)

	# send an embed that starts a new turn
	async def send_turn_embed(self, ctx, game, **kwargs):
		game.turn_embed = game.create_embed(**kwargs)
		game.turn_msg = await ctx.send(embed=game.turn_embed)


	async def on_reaction_add(self, reaction, user):
		if reaction.message.channel.id not in self.games:
			return
		game = self.games[reaction.message.channel.id]
		with await game.state_lock:	
			if game.vote_msg is None or game.vote_time <= 0:
				return
			self._on_reaction(game, reaction, user, 1)
			
			# also handle voting logic
			ctx = await self.bot.get_context(reaction.message)
			if game.vote_correct:
				if game.fail_tally > .5 * len(game.players):
					await ctx.send(f"The decision was overruled! Player {game.vote_player.mention} is given a strike!")
					await self.strike(ctx, game, game.vote_player)
					game.vote_time = -1
			else:
				if game.pass_tally >= .5 * len(game.players):
					game.picked.append(game.last_team)
					game.number = game.last_team % 10
					game.next_turn()
					await self.send_turn_embed(ctx, game,
						title="Team correct!",
						description=f"Team {game.last_team} ({game.last_name}) was correct! Moving onto the next player as follows.",
						color=discord.Color.green(),
					)
					game.vote_time = -1
				elif game.fail_tally >= .5 * len(game.players):
					await ctx.send(f"Team {game.last_team} was guessed wrong! Strike given to the responsible player and player is skipped.")
					await self.skip_player(ctx, game, game.current_turn())
					game.vote_time = -1



	async def on_reaction_remove(self, reaction, user):
		if reaction.message.channel.id not in self.games:
			return
		game = self.games[reaction.message.channel.id]

		with await game.state_lock:
			if game.vote_msg is None or game.vote_time <= 0:
				return
			self._on_reaction(game, reaction, user, -1)
		
	def _on_reaction(self, game, reaction, user, inc):
		# as they say, don't repeat yourself
		# also, as this is just manipulating memory, it's not async

		if reaction.message.id == game.vote_msg.id and user in game.players:
			if reaction.emoji == '❌':
				game.fail_tally += inc
			
			if reaction.emoji == '✅':
				game.pass_tally += inc
		return game
	
	@keep_alive
	async def game_turn_countdown(self, ctx, game):
		await asyncio.sleep(1)
		with await game.state_lock:
			if not game.running:# or game.time <= 0:
				return
			print(f"game.time == {game.time}")
			game.time -= 1
			game.turn_embed.set_field_at(3, name="Time Left", value=game.time)

			if game.vote_time > 0 and game.vote_correct:
				game.vote_time -= 1
				game.turn_embed.set_field_at(4, name="Voting Time", value=game.vote_time)
				
			if game.time % 5 == 0:
				await game.turn_msg.edit(embed=game.turn_embed)

			if game.time == 0:
				await self.skip_player(ctx, game, game.current_turn())
				return
			game.turn_task = self.bot.loop.create_task(self.game_turn_countdown(ctx, game))

		
	@keep_alive	
	async def game_vote_countdown(self, ctx, game):
		await asyncio.sleep(1)
		with await game.state_lock:
			if not (game.running and not game.vote_correct and game.vote_embed and game.vote_time > 0):
				return
			#print(f"game.vote_time == {game.vote_time}")
			game.vote_time -= 1
			game.vote_embed.set_field_at(5, name="Voting Time", value=game.vote_time)
			if game.vote_time % 5 == 0:
				await game.vote_msg.edit(embed=game.vote_embed)
			if game.vote_time == 0:
				await ctx.send("The vote did not reach 50% in favor or in failure, so the responsible player is given a strike and skipped.")
				await self.skip_player(ctx, game, game.current_turn())

			game.vote_task = self.bot.loop.create_task(self.game_vote_countdown(ctx, game))
class NameGameDefaultMode(db.DatabaseObject):
	__tablename__ = "namegame_defaultmode"
	guild_id = db.Column(db.Integer, primary_key=True)
	mode = db.Column(db.String)
class NameGameChannel(db.DatabaseObject):
	__tablename__ = "namegame_channel"
	guild_id = db.Column(db.Integer, primary_key=True)
	channel_id = db.Column(db.Integer, nullable=True)

class NameGameLeaderboard(db.DatabaseObject):
	__tablename__ = "namegame_leaderboard"
	user_id = db.Column(db.Integer, primary_key=True)
	wins = db.Column(db.Integer)
	game_mode = db.Column(db.String)

def setup(bot):
	bot.add_cog(NameGame(bot))
