=========
Starboard
=========
starboard
+++++++++
Show the current server's starboard configuration. A starboard (or a
hall of fame) is a channel the bot will repost messages in if they
receive a certain number         of configured reactions.  To configure
a starboard, use the `starboard config` subcommand.
::
   `{prefix}starboard` - Get the current starboard settings for this server
add
+++
Add a message to the starboard manually
::
   `{prefix}starboard add 1285719825125 #channel` - add message with id `1285719825125` in `#channel` to the starboard 
manually.
disable
+++++++
Turn off the starboard if it is enabled
::
   `{prefix}starboard disable` - disables the starboard for the current server
config
++++++
Modify the settings for this server's starboard
::
   `{prefix}starboard config #hall-of-fame 🌟 5` - Set the bot to repost messages that have 5 star reactions to `#hall-of-fame
`{prefix}starboard config #hall-of-fame 🌟 5 ❌` - Same as above, but with a extra X cancel emoji 
