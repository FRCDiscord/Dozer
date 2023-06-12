==========
Management
==========
schedulesend
++++++++++++
Allows a message to be sent at a particular time Commands: add, delete,
list
::

list
++++
Displays currently scheduled messages
::
   `{prefix}schedulesend list`: Lists all scheduled messages for the current guild
add
+++
Allows a message to be sent at a particular time Headers are
distinguished by the characters `-/-`
::
   `{prefix}schedulesend add #announcments "1/0/1970 0:00:00 GMT" Epoch -/- 00000`: Dozer will send a message on the unix epoch in #announcments
delete
++++++
Delete a scheduled message
::
   `{prefix}schedulesend delete 5`: Deletes the scheduled message with the ID of 5
