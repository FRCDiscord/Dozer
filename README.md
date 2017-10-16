# Dozer
Omnipotent guild management bot for FIRST Discord servers

## Setup
These directions use `python3` as the python executable. On Windows, this could be `python` or `py`.
1. Install dependencies with `python3 -m pip install -Ur requirements.txt`
1. Run the bot once with `python3 -m dozer`. This will crash, but generate a default config file.
1. Add the Discord bot account's token to `discord_token` in the config.
1. Add your ID, and anyone else's ID who should be able to use the developer commands, to the list `developers` in the config.
1. Run the bot again, you should see `Signed in as username#discrim (id)` after a few seconds.
