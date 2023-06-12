===========
Development
===========
reload
++++++
Reloads a cog.
::
   `{prefix}reload development` - reloads the development cog
document
++++++++
Dump documentation for Sphinx processing
::
   `{prefix}document` - Runs the documentation cycle
eval
++++
Evaluates Python. Await is valid and `{ctx}` is the command context.
::
   `{prefix}eval 0.1 + 0.2` - calculates 0.1 + 0.2
   `{prefix}eval await ctx.send('Hello world!')` - send "Hello World!" to this channel
su
++
Execute a command as another user.
::
   `{prefix}su cooldude#1234 {prefix}ping` - simulate cooldude sending `{prefix}ping`
