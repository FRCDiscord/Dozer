=====
Roles
=====
giveme
++++++
Give you one or more giveable roles, separated by commas.
::
   `{prefix}giveme Java` - gives you the role called Java, if it exists
`{prefix}giveme Java, Python` - gives you the roles called Java and Python, if they exist
list
++++
Lists all giveable roles for this server.
::
   `{prefix}giveme list` - lists all giveable roles
add
+++
Makes an existing role giveable, or creates one if it doesn't exist.
Name must not contain commas. Similar to create, but will use an
existing role if one exists.
::
   `{prefix}giveme add Java` - creates or finds a role named "Java" and makes it giveable
`{prefix}giveme Java` - gives you the Java role that was just found or created
delete
++++++
Deletes and removes a giveable role.
::
   `{prefix}giveme removefromlist Java` - removes the role "Java" from the list of giveable roles but does not remove it from the server or members who have it 
removefromlist
++++++++++++++
Deletes and removes a giveable role.
::
   
purge
+++++
Force a purge of giveme roles that no longer exist in the guild
::
   
remove
++++++
Removes multiple giveable roles from you. Names must be separated by
commas.
::
   `{prefix}giveme remove Java` - removes the role called "Java" from you (if it can be given with `{prefix}giveme`)
`{prefix}giveme remove Java, Python` - removes the roles called "Java" and "Python" from you
create
++++++
Create a giveable role. Name must not contain commas. Similar to add,
but will always create a new role.
::
   `{prefix}giveme create Python` - creates a role named "Python" and makes it giveable
`{prefix}giveme Python` - gives you the Python role that was just created
tempgive
++++++++
Temporarily gives a member a role for a set time. Not restricted to
giveable roles.
::
   `{prefix}tempgive cooldude#1234 1h Java` - gives cooldude any role, giveable or not, named Java for one hour
give
++++
Gives a member a role. Not restricted to giveable roles.
::
   `{prefix}give cooldude#1234 Java` - gives cooldude any role, giveable or not, named Java
take
++++
Takes a role from a member. Not restricted to giveable roles.
::
   `{prefix}take cooldude#1234 Java` - takes any role named Java, giveable or not, from cooldude
rolemenu
++++++++
Base command for setting up and tracking reaction roles
::
   `{prefix}rolemenu createmenu #roles Example role menu`: Creates an empty role menu embed
`{prefix}rolemenu addrole <message id> @robots 🤖:` adds the reaction role 'robots' to the target message 
`{prefix}rolemenu delrole <message id> @robots:` removes the reaction role 'robots' from the target message
createmenu
++++++++++
Creates a blank reaction role menu
::
   `{prefix}rolemenu createmenu #roles Example role menu`: Creates an empty role menu embed
delrole
+++++++
Removes a reaction role from a message or a role menu
::
   -----To target a role menu use this format-----
`{prefix}rolemenu delrole <message id> <@robots or "Robots">`
-----To target a custom message use this format-----
`{prefix}rolemenu delrole <channel> <message id> <@robots or "Robots">`
addrole
+++++++
Adds a reaction role to a message or a role menu
::
   -----To target a role menu use this format-----
 `{prefix}rolemenu addrole <message id> <@robots or "Robots"> 🤖`
-----To target a custom message use this format-----
 `{prefix}rolemenu addrole <channel> <message id> <@robots or "Robots"> 🤖`
 
