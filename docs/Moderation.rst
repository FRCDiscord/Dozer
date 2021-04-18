==========
Moderation
==========
warn
++++
Sends a message to the mod log specifying the member has been warned
without punishment.
::
   `{prefix}`warn @user reason - warns a user for "reason"
customlog
+++++++++
Sends a message to the mod log with custom text.
::
   `{prefix}`customlog reason - warns a user for "reason"
timeout
+++++++
Set a timeout (no sending messages or adding reactions) on the current
channel.
::
   `{prefix}timeout 60` - prevents sending messages in this channel for 1 minute (60s)
prune
+++++
Bulk delete a set number of messages from the current channel.
::
   `{prefix}prune 10` - Delete the last 10 messages in the current channel.
`{prefix}prune 786324930378727484` - Deletes all messages up to that message ID
punishments
+++++++++++
List currently active mutes and deafens in a guild
::
   `{prefix}punishments:` Lists currently active punishments in current guild
ban
+++
Bans the user mentioned.
::
   `{prefix}ban @user reason - ban @user for a given (optional) reason
unban
+++++
Unbans the user mentioned.
::
   `{prefix}unban user_id reason - unban the user corresponding to the ID for a given (optional) reason
kick
++++
Kicks the user mentioned.
::
   `{prefix}kick @user reason - kick @user for a given (optional) reason
mute
++++
Mute a user to prevent them from sending messages
::
   `{prefix}mute @user 1h reason` - mute @user for 1 hour for a given reason, the timing component (1h) and reason is optional.
unmute
++++++
Unmute a user to allow them to send messages again.
::
   `{prefix}unmute @user reason - unmute @user for a given (optional) reason
deafen
++++++
Deafen a user to prevent them from both sending messages but also
reading messages.
::
   `{prefix}deafen @user 1h reason` - deafen @user for 1 hour for a given reason, the timing component (1h) is optional.
selfdeafen
++++++++++
Deafen yourself for a given time period to prevent you from reading or
sending messages; useful as a study tool.
::
   `{prefix}selfdeafen time (1h5m, both optional) reason`: deafens you if you need to get work done
undeafen
++++++++
Undeafen a user to allow them to see message and send message again.
::
   `{prefix}undeafen @user reason - undeafen @user for a given (optional) reason
voicekick
+++++++++
Kick a user from voice chat. This is most useful if their perms to
rejoin have already been removed.
::
   `{prefix}voicekick @user reason` - kick @user out of voice
purgenm
+++++++
Manually run a new member purge
::
   
modlogconfig
++++++++++++
Set the modlog channel for a server by passing the channel id
::
   `{prefix}modlogconfig #join-leave-logs` - set a channel named #join-leave-logs to log joins/leaves 
nmconfig
++++++++
Sets the config for the new members channel
::
   `{prefix}nmconfig #new_members Member I have read the rules and regulations` - Configures the #new_members channel 
so if someone types "I have read the rules and regulations" it assigns them the Member role. 
nmpurgeconfig
+++++++++++++
Sets the config for the new members purge
::
   `{prefix}nmpurgeconfig Members 90: Kicks everyone who doesn't have the members role 90 days after they join.
memberconfig
++++++++++++
Set the member role for the guild. The member role is the role used for
the timeout command. It should be a role that all members of the server
have.
::
   `{prefix}memberconfig Members` - set a role called "Members" as the member role
`{prefix}memberconfig @everyone` - set the default role as the member role
`{prefix}memberconfig everyone` - set the default role as the member role (ping-safe)
`{prefix}memberconfig @ everyone` - set the default role as the member role (ping-safe)
`{prefix}memberconfig @.everyone` - set the default role as the member role (ping-safe)
`{prefix}memberconfig @/everyone` - set the default role as the member role (ping-safe)
linkscrubconfig
+++++++++++++++
Set a role that users must have in order to post links. This accepts the
safe default role conventions that the memberconfig command does.
::
   `{prefix}linkscrubconfig Links` - set a role called "Links" as the link role
`{prefix}linkscrubconfig @everyone` - set the default role as the link role
`{prefix}linkscrubconfig everyone` - set the default role as the link role (ping-safe)
`{prefix}linkscrubconfig @ everyone` - set the default role as the link role (ping-safe)
`{prefix}linkscrubconfig @.everyone` - set the default role as the link role (ping-safe)
`{prefix}linkscrubconfig @/everyone` - set the default role as the link role (ping-safe)
crossbans
+++++++++
Cross ban
::
   
subscribe
+++++++++
Subscribe to a guild to cross ban from
::
   
unsubscribe
+++++++++++
Remove cross ban subscription
::
   
