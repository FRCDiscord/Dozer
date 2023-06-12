=====
Teams
=====
setteam
+++++++
Sets an association with your team in the database.
::
   `{prefix}setteam type team_number` - Creates an association in the database with a specified team
removeteam
++++++++++
Removes an association with a team in the database.
::
   `{prefix}removeteam type team_number` - Removes your associations with a specified team
teamsfor
++++++++
Allows you to see the teams for the mentioned user, or yourself if
nobody is mentioned.
::
   `{prefix}teamsfor member` - Returns all team associations with the mentioned user. Assumes caller if blank.
compcheck
+++++++++
Allows you to see people in the Discord server that are going to a
certain competition.
::
   `{prefix}compcheck frc 2019txaus` - Returns all members on teams registered for 2019 Austin District Event
   `{prefix}compcheck ftc 1920-TX-AML2` - Returns all members on teams registered for the 2020 Austin Metro League Championship Dell Division
onteam
++++++
Allows you to see who has associated themselves with a particular team.
::
   `{prefix}onteam type team_number` - Returns a list of users associated with a given team type and number
onteam_top
++++++++++
Show the top 10 teams by number of members in this guild.
::
   `{prefix}onteam_top` - List the 10 teams with the most members in this guild
toggleautoteam
++++++++++++++
Toggles automatic adding of team association to member nicknames
::

