=========
Actionlog
=========
messagelogconfig
++++++++++++++++
Set the modlog channel for a server by passing the channel id
::
   `{prefix}messagelogconfig #orwellian-dystopia` - set a channel named #orwellian-dystopia to log message edits/deletions
memberlogconfig
+++++++++++++++
Command group to configure Join/Leave logs
::
   `{prefix}memberlogconfig setchannel channel`: Sets the member log channel 
   `{prefix}memberlogconfig toggleping`: Toggles whenever members are pinged upon joining the guild
   `{prefix}memberlogconfig setjoinmessage template`: Sets join template
   `{prefix}memberlogconfig setleavemessage template`: Sets leave template
   `{prefix}memberlogconfig help`: Returns the template formatting key
setjoinmessage
++++++++++++++
Configure custom join message template
::

help
++++
Displays message formatting key
::

toggleping
++++++++++
Toggles whenever a new member gets pinged on join
::

setleavemessage
+++++++++++++++
Configure custom leave message template
::

togglesendonverify
++++++++++++++++++
Toggles if a join log is sent on user joining or on completing
verification
::

viewconfig
++++++++++
Command to view Join/Leave logs configuration.
::

disable
+++++++
Disables Join/Leave logging
::

setchannel
++++++++++
Configure join/leave channel
::

locknickname
++++++++++++
Locks a members nickname to a particular string, in essence revoking
nickname change perms
::
   `{prefix}locknickname @Snowplow#5196 Dozer`: Locks user snowplows nickname to "dozer"
unlocknickname
++++++++++++++
Removes nickname lock from member
::
   `{prefix}unlocknickname @Snowplow#5196`: Removes nickname lock from user dozer
