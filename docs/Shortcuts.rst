=========
Shortcuts
=========
settings
++++++++
Display the shortcut settings for the current server.
::
   `{prefix}shortcuts settings` - display the shortcut settings for the current server
setprefix
+++++++++
Set the prefix to be used to respond to shortcuts for the server.
::
   `{prefix}shortcuts setprefix ^` - sets the server's shortcut prefix to "^"
set
+++
Sets the reply for a given shortcut name, creating one if doesn't exist.
::
   `{prefix}shortcuts set foo bar` - sets the shortcut named "foo" to send "bar"
remove
++++++
Removes a shortcut from the server.
::
   `{prefix}shortcuts remove foo` - removes the shortcut "foo" for the server
list
++++
Lists the shortcuts for the server.
::
   `{prefix}shortcuts list` - lists the shortcuts that exist for the server
