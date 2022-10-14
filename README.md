# Dozer
![CI](https://github.com/FRCDiscord/Dozer/workflows/CI/badge.svg)

Omnipotent guild management bot for FIRST Discord servers

Table of Contents
=================

   * [Dozer](#dozer)
      * [Setup](#setup)
         * [Installing Python 3.8](#installing-python-38)
            * [Manually](#manually)
            * [Using pyenv](#using-pyenv)
         * [Getting your Discord Bot Token](#getting-your-discord-bot-token)
         * [Getting Optional API Keys](tokenInstructions.md)
         * [Setting up the bot](#setting-up-the-bot)
         * [Adding the bot to your server](#adding-the-bot-to-your-server)
      * [Development](#development)

## Setup

### Installing Python 3.8

run `python -V` to find what version of python you are running. If you are running version 3.8 or newer, feel free to skip this section

#### Manually

[Unix](https://docs.python.org/3/using/unix.html?highlight=install)

[Windows](https://docs.python.org/3/using/windows.html)

run `python -V` to ensure that version 3.8 or newer is installed. 

#### Using pyenv

Many distributions do not have python 3.8 in their repositories yet. If this is the case for you, then [pyenv](https://github.com/pyenv/pyenv) is a great option for managing different python versions.

Instructions for installing are located [here](https://github.com/pyenv/pyenv-installer).

1. `pyenv install 3.8.2` downloads and builds a newer version of python
2. `pyenv global 3.8.2` sets 3.8.2 as the primary version for the current user
3. run `python -V` to ensure that version 3.8 or newer is installed. 

Through the rest of this README, we will assume that you have found the correct `python` executable for your setup and are using it accordingly.

### Installing PostgreSQL

As of May 13, 2020 , Dozer no longer supports database types other than PostgreSQL. This means installations using SQLite
(as was default), will need to migrated, as well as new installations will have to have PostgreSQL installed on the 
machine for development or production. You can install PostgreSQL for your platform [here](https://www.postgresql.org/download/)

### Getting your Discord Bot Token

1. Go to the [Discord Developer Portal](https://discordapp.com/developers/applications/me) and create a new application by clicking the button. Enter a name for the application when prompted.
    ![creating a new discord app](static/newapp.png)

2. Create a bot user inside of your application. 
   In the settings menu, go to the "Bot" menu.
   ![creating a bot user 1](static/createbot1.png)
   
   Within the bot menu, select the "create bot user" option.
   ![creating a bot user 2](static/createbot2.png)

3. Copy the bot user token (seen in the image below) - We'll need that later!
   Do not share your token with anyone. If someone obtains your bot user token, they gain full control of your bot. Be careful!
   ![token](static/tokens.png)

4. Within your bot user settings, make sure both "intents" settings are enabled.
   ![enabling intents](static/intents.png)


### Setting up the bot

Setup configuration options:
- Dozer can be set up manually, with Python, or with Docker. 
- Docker allows you to run programs the exact same way on different platforms using [containers](https://www.docker.com/resources/what-container). **Docker also allows Dozer to set up many of the dependencies** (particularly lavalink, which is used for the music functionality) **automatically.** To use Dozer with the Docker configuration

1. If you are using Docker, download and install it for your platform [here](https://www.docker.com/products/docker-desktop). Additional documentation can be found [here](https://docs.docker.com/desktop/), if needed.

2. Open your command line/terminal interface and go to the directory where Dozer's code is located.
   1. If you're not familiar with how to do that:
      1. On Windows, open CMD or Powershell. On Mac and Linux, open the Terminal. and type `cd "path/to/directory"`.
         Alternatively, on Windows, go to the directory in the File Explorer app. Click the bar that is circled in the image below and type `cmd`. Press enter and the command line should open up within that directory. Also, you can use an integrated terminal with an IDE of your choice.
         ![open the cmd within a directory](static/fileExplorerBar.png)

3. Install dependencies with `python -m pip install -Ur requirements.txt` in your command line interface.
   1. If that doesn't work, try replacing `python` with `python3`.

4. Run the bot once with `python -m dozer`. This will crash, but generate a default config file.
   1. Dozer uses [json](http://www.json.org/) for its config file

5. Add the Discord bot account's token to `discord_token` in `config.json`

6. If you have a Google Maps API key, a Blue Alliance API key, an Orange Alliance API key, a Twitch API client ID and client secret, and/or a Reddit client ID and client secret, add them to the appropriate places in `config.json`. For more details on how to get these API keys, [see this file for instructions](tokenInstructions.md). ***If you don't, your bot will still work,*** but you won't be able to use the commands that rely on these tokens.

7. If you are using Docker, you most likely won't have to do anything. Otherwise, add your database connection info to `db_url` in `config.json` using the following format:
    
   ```postgres://user:password@host:port```
    
   Replace `host` with your database IP, or `localhost` if it's on the same PC. `port` is by default 5432. If the user has no password, you can remove the colon and password. The default user for the above installation is `postgres`, however we strongly suggest making a `dozer` user for security reasons using [this guide](https://www.postgresql.org/docs/current/app-createuser.html).

8. Add your Discord user ID, and anyone else's ID who should be able to use the developer commands, to the list `developers` in `config.json`
   1. Be careful giving this out. Developers can control everything your bot does and potentially get your [bot user token!](#getting-your-discord-bot-token)

9. The default command prefix is &. If this is already in use on your server or you would like another prefix, you can change the `prefix` value in `config.json`.

10. To configure lavalink:
* **If you are using Docker,** Open up Docker Desktop and find the lavalink container's name. Change the host IP listed in `config.json` to that name. For example, in the following image below, the config.json file should say `"host": "dozerRecent_lavalink_1"`. Set the `port` value to the port that's listed in `docker-compose.yml`.
   
   ![Finding the lavalink container name](static/containerNames.png)

* **If you are not using Docker**, set the `host` and `port` values to which values that you have set up.

11. Run the bot again. If you're using Docker, run `docker-compose up` twice in your command line interface. If you are setting it up manually, repeat the command in step 4. You should see `Signed in as username#discrim (id)` after a few seconds.
12. When using Docker:
    1. Make sure the Docker for Desktop client is running. On Windows, you have to open up the app and either skip the tutorial or follow it when running it for the first time, and then you can run the command. (Note: it's not necessary to do the tutorial.) By default, Docker runs in the background after that first startup, so you should be fine.
    2. The first time you run `docker-compose up`, you are building it and the bot won't go online. Once the building process seems to be done, press ctrl+C and run the command again.
    3. As of this writing, `Signed in as` message is pretty far up, as seen highlighted in orange in the image below.
    4. Sometimes, the bot can't connect to the lavalink IP, as circled in blue in the image below. In that case, simply run the bot command `{prefix}restart` and it should work.
![dockerstartup](static/dockerstartup.png)

### Adding the bot to your server

1. Within the scopes menu under OAuth2, select the "bot" scope
   ![selecting scopes](static/invite1_scopes.png)

2. A new "permissions" menu should appear below. Select all the permissions that you want your instance of Dozer to have. If you want all permissions and you trust your instance wholeheartedly, select "Administrator"
   ![permissions](static/invite2_permissions.png)

3. The bottom of the scopes menu should have a URL. Copy and paste that URL into a new tab in your browser. It'll open a page where you can invite a bot to your server.
   ![oauthInvite](static/invite3_oauthurl.png)

### Setting up the database systems
Dozer requires Postgres. You can set up Postgres on your own server or use a service such as ElephantSQL. To make it work in Dozer, 
install the psycopg2 pip package, then change the `db_url` key in `config.json` to a URL that follows this format: 
`postgresql://username:password@host/db_name_in_postgres` with the correct information filled in.

## Development

1. pylint
   1. Pylint should be installed with ```pip install pylint```, if it is not already installed. 
   2. Before code can be merged, it must pass pylint with a score of 100%. 
   3. You can run a pylint check manually, or it will be run by pre-commit before you commit.
2. pre-commit
   1. pre-commit should be installed with ```pip install pre-commit```
   2. You should then install the pre-commit hooks with ```pre-commit install```
   3. When you commit this will only check the files you edited this commit, you may still fail a full pylint check. 
