=====
Voice
=====
autoptt
+++++++
Configures AutoPtt limit for when members join/leave voice channels ptt
is enabled
::
   `{prefix}autoptt "General #1" 15 - sets up Dozer to give force Push-To-Talk when more than 15 users joins a voice channel.
`{prefix}autoptt "General #1" 0 - disables AutoPTT for General #1.
voicebind
+++++++++
Binds a voice channel with a role, so users joining voice channels will
be given desired role(s).
::
   `{prefix}voicebind "General #1" voice-general-1` - sets up Dozer to give users  `voice-general-1` when they join voice channel "General #1", which will be removed when they leave.
voiceunbind
+++++++++++
Dissasociates a voice channel with a role previously binded with the
voicebind command.
::
   `{prefix}voiceunbind "General #1"` - Removes automatic role-giving for users in "General #1".
voicebindlist
+++++++++++++
Lists all the voice channel to role bindings for the current server
::
   `{prefix}voicebindlist` - Lists all the voice channel to role bindings for the current server bound with the voicebind command.
