========
NameGame
========
ng
++
Show info about and participate in a robotics team namegame. Run the
help command on each of the subcommands for more detailed help. List of
subcommands:     ng info     ng startround     ng addplayer     ng pick
ng drop     ng skip     ng gameinfo
::
   `{prefix}ng` - show a description on how the robotics team namegame works. 
skip
++++
Skips the current player if the player wishes to forfeit their turn.
::
   `{prefix}ng skip` - skip the current player's turn
startround
++++++++++
Starts a namegame session. One can select the robotics program by
specifying one of "FRC" or "FTC".
::
   `{prefix}ng startround frc` - start an FRC namegame session.
info
++++
Show a description of the robotics team name game and how to play.
::
   `{prefix}ng help` - show a description on how the robotics team namegame works
drop
++++
Drops a player from the current game by eliminating them. Once dropped,
they can no longer rejoin.
::
   `{prefix}ng drop` - remove the initiator of the command from the current game
gameinfo
++++++++
Display info about the currently running game.
::
   `{prefix}ng gameinfo` - display info about the currently running game.
unheck
++++++
Emergency removal of a haywire session.
::

leaderboard
+++++++++++
Display top numbers of wins for the specified game mode
::
   `{prefix}ng leaderboard ftc` - display the namegame winning leaderboards for FTC.
config
++++++
Configuration for namegame
::

defaultmode
+++++++++++
Configuration of the default game mode (FRC, FTC, etc.)
::

addplayer
+++++++++
Add players to the current game. Only works if the user is currently
playing.
::
   `{prefix}ng addplayer @user1, @user2` - add user1 and user2 to the game.
modes
+++++
Returns a list of supported modes
::

pick
++++
Attempt to pick a team in a game.
::
   `{prefix}ng pick 254 poofy cheeses` - attempt to guess team 254 with a specified name of "poofy cheeses".
