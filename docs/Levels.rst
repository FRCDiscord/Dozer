======
Levels
======
meesyncs
++++++++
Function to scrap ranking data from the mee6 api and save it to the
database
::
   `{prefix}meesyncs`: Sync ranking data from the mee6 API to dozer's database
checkrolelevels
+++++++++++++++
Displays all level associated roles
::
   `{prefix}checkrolelevels`: Returns an embed of all the role levels 
adjustlevels
++++++++++++
Allows for moderators to adjust a members level/xp
::
   `{prefix}adjustlevels setlevel <@Snowplow or "Snowplow"> 15`:
Sets member Snowplow's level to 15 
   `{prefix}adjustlevels adjustxp <@Snowplow or "Snowplow"> -1500`:
Adjusts member Snowplow's xp by -1500xp 
   `{prefix}adjustlevels swapxp <@Snowplow or "Snowplow"> <@Dozer or "Dozer">`:
Swaps Snowplow's xp with Dozer's xp
   `{prefix}adjustlevels transferxp <@Snowplow or "Snowplow"> <@Dozer or "Dozer">`:
Adds Snowplow's xp to dozer's xp
   
transferxp
++++++++++
Adds xp from one member to another member
::
   
swapxp
++++++
Swap xp stats between two members in a guild
::
   
setlevel
++++++++
Changes a members level to requested level
::
   
adjustxp
++++++++
Adjusts a members xp by a certain amount
::
   
configureranks
++++++++++++++
Configures dozer ranks:tm:
::
   `{prefix}configureranks`: Returns current configuration
`{prefix}configureranks xprange 5 15`: Sets the xp range
`{prefix}configureranks setcooldown 15`: Sets the cooldown time in seconds
`{prefix}configureranks toggle`: Toggles levels
`{prefix}configureranks keeproles`: Toggles whenever old level role roles will be kept on level up
`{prefix}configureranks notificationchannel channel`: Sets level up message channel
`{prefix}configureranks notificationsoff`: Turns off notification channel
`{prefix}configureranks setrolelevel role level`: Adds a level role
`{prefix}configureranks delrolelevel role`: Deletes a level role 
toggle
++++++
Toggle dozer ranks
::
   
notificationsoff
++++++++++++++++
Turns off level up messages
::
   
setrolelevel
++++++++++++
Sets a role to be given to a user when they reach a certain level
::
   `{prefix}setrolelevel "level 2" 2`: Will configure the role "level 2" to be given to users who reach level 2` 
removerolelevel
+++++++++++++++
Removes a levelrole
::
   `{prefix}removerolelevel level 2 `: Will remove role "level 2" from level roles
xprange
+++++++
Set the range of a servers levels random xp
::
   
keeproles
+++++++++
Toggles whenever old level role roles will be kept on level up
::
   
setcooldown
+++++++++++
Set the time in seconds between messages before xp is calculated again
::
   
notificationchannel
+++++++++++++++++++
Set up the channel where level up messages are sent
::
   
rank
++++
Get a user's ranking on the XP leaderboard. If no member is passed, the
caller's ranking is shown.
::
   `{prefix}rank`: show your ranking
`{prefix}rank coolgal#1234`: show another user's ranking
levels
++++++
Show the XP leaderboard for this server. Leaderboard refreshes every 5
minutes or so
::
   `{prefix}levels`: show the XP leaderboard
`{prefix}levels SnowPlow[>]#5196`: Jump to Snowplow's position on the leaderboard
