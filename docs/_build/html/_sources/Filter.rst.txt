======
Filter
======
filter
++++++
List and manage filtered words
::
   `{prefix}filter add test` - Adds test as a filter.
`{prefix}filter remove 1` - Removes filter 1
`{prefix}filter dm true` - Any messages containing a filtered word will be DMed
`{prefix}filter whitelist` - See all of the whitelisted roles
`{prefix}filter whitelist add Administrators` - Make the Administrators role whitelisted for the filter.
`{prefix}filter whitelist remove Moderators` - Make the Moderators role no longer whitelisted.
remove
++++++
Remove a pattern from the filter list.
::
   `{prefix}filter remove 7` - Disables filter with ID 7
dm
++
Set whether filter words should be DMed when used in bot messages
::
   `{prefix}filter dm_config True` - Makes all messages containining filter lists to be sent through DMs
add
+++
Add a pattern to the filter using RegEx. Any word can be added and is
tested case-insensitive.
::
   `{prefix}filter add Swear` - Makes it so that "Swear" will be filtered
whitelist
+++++++++
List all whitelisted roles for this server
::
   `{prefix}filter whitelist` - Lists all the whitelisted roles
add
+++
Add a role to the whitelist
::
   `{prefix}filter whitelist add Moderators` - Makes it so that Moderators will not be caught by the filter.
remove
++++++
Remove a role from the whitelist
::
   `{prefix}filter whitelist remove Admins` - Makes it so that Admins are caught by the filter again.
edit
++++
Edit an already existing filter using a new pattern. A filter's friendly
name cannot be edited.
::
   `{prefix}filter edit 4 Swear` - Change filter 4 to filter out "Swear" instead of its previous pattern
