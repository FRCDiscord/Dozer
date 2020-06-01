"""Initializes the bot and deals with the configuration file"""

import json
import os
import sys
import asyncio
from .db import db_init, db_migrate

from . import db

config = {
    'prefix': '&', 'developers': [],
    'tba': {
        'key': ''
    },
    'toa': {
        'key': 'Put TOA API key here',
        'app_name': 'Dozer',
    },
    'db_url': 'postgres://POSTGRES URL HERE',
    'gmaps_key': "PUT GOOGLE MAPS API KEY HERE",
    'discord_token': "Put Discord API Token here.",
    'is_backup': False
}
config_file = 'config.json'

if os.path.isfile(config_file):
    with open(config_file) as f:
        config.update(json.load(f))


with open('config.json', 'w') as f:
    json.dump(config, f, indent='\t')

asyncio.get_event_loop().run_until_complete(db_init(config['db_url']))


if 'discord_token' not in config:
    sys.exit('Discord token must be supplied in configuration')

if sys.version_info < (3, 6):
    sys.exit('Dozer requires Python 3.6 or higher to run. This is version %s.' % '.'.join(sys.version_info[:3]))

from . import Dozer  # After version check

bot = Dozer(config)

for ext in os.listdir('dozer/cogs'):
    if not ext.startswith(('_', '.')):
        bot.load_extension('dozer.cogs.' + ext[:-3])  # Remove '.py'

asyncio.get_event_loop().run_until_complete(db_migrate())

bot.run()

# restart the bot if the bot flagged itself to do so
if bot._restarting:
    script = sys.argv[0]
    if script.startswith(os.getcwd()):
        script = script[len(os.getcwd()):].lstrip(os.sep)

    if script.endswith('__main__.py'):
        args = [sys.executable, '-m', script[:-len('__main__.py')].rstrip(os.sep).replace(os.sep, '.')]
    else:
        args = [sys.executable, script]
    os.execv(sys.executable, args + sys.argv[1:])
