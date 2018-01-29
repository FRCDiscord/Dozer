import json, os.path, sys
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

if 'discord_token' not in config:
	sys.exit('Discord token must be supplied in configuration')

if sys.version_info < (3, 6):
	sys.exit('Dozer requires Python 3.6 or higher to run. This is version %s.' % '.'.join(sys.version_info[:3]))

from . import Dozer # After version check

bot = Dozer(config)

for ext in os.listdir('dozer/cogs'):
	if not ext.startswith(('_', '.')):
		bot.load_extension('dozer.cogs.' + ext[:-3]) # Remove '.py'

db.DatabaseObject.metadata.create_all()

bot.run()
