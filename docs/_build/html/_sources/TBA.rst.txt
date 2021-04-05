===
TBA
===
tba
+++
Get FRC-related information from The Blue Alliance. If no subcommand is
specified, the `team` subcommand is inferred, and the argument is taken
as a team number.
::
   `{prefix}tba 5052` - show information on team 5052, the RoboLobos
raw
+++
Get raw TBA API output for a team. This command is really only useful
for development.
::
   `{prefix}tba raw 4150` - show raw information on team 4150, FRobotics
eventsfor
+++++++++
Get the events a team is registered for a given year. Defaults to
current (or upcoming) year.
::
   `{prefix}tba eventsfor 1533` - show the currently registered events for team 1533, Triple Strange
media
+++++
Get media of a team for a given year. Defaults to current year.
::
   `{prefix}tba media 971 2016` - show available media from team 971 Spartan Robotics in 2016
awards
++++++
Gets a list of awards the specified team has won during a year.
::
   `{prefix}tba awards 1114` - list all the awards team 1114 Simbotics has ever gotten.
team
++++
Get information on an FRC team by number.
::
   `{prefix}tba team 4131` - show information on team 4131, the Iron Patriots
weather
+++++++
Finds the current weather for a given team.
::
   `{prefix}weather frc 5052` - show the current weather for FRC team 5052, The RoboLobos
`{prefix}weather ftc 15470` - show the current weather for FTC team 15470 
timezone
++++++++
Get the timezone of a team based on the team number.
::
   `{prefix}timezone frc 5052` - show the local time of FRC team 5052, The RoboLobos
`{prefix}timezone ftc 15470` - show the local time of FTC team 15470
