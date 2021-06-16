====
News
====
news
++++
Show help for news subscriptions
::
   `{prefix}news` - Get a small guide on using the News system
restart_loop
++++++++++++
Restart the news check loop
::
   `{prefix}news restart_loop` - Restart the news loop if you are a developer
remove
++++++
Remove a subscription of a given source from a specific channel
::
   `{prefix}news remove #news cd` - Remove the subscription of Chief Delphi to #news
`{prefix}news remove #reddit reddit frc` - Remove the subscription of /r/FRC to #reddit
next_run
++++++++
Print out the next time the news check loop will run
::
   `{prefix}news next_run` - Check the next time the loop runs if you are a developer
sources
+++++++
List all available sources to subscribe to.
::
   `{prefix}`news sources` - Get all available sources
get_exception
+++++++++++++
If the news check loop has failed, print out the exception and traceback
::
   `{prefix}news get_exception` - Get the exception that the loop failed with
subscriptions
+++++++++++++
List all subscriptions that the current server are subscribed to
::
   `{prefix}news subs` - Check all subscriptions in the current server
`{prefix}news subs #news` - See all the subscriptions for #news
add
+++
Add a new subscription of a given source to a channel.
::
   `{prefix}news add #news cd` - Make new Chief Delphi posts appear in #news
`{prefix}news add #announcements frc plain` - Add new FRC blog posts in plain text to #announcements
`{prefix}news add #reddit reddit embed frc` - Add new posts from /r/FRC to #reddit
