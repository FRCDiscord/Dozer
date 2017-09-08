import json, os.path, sys

config = {'prefix': '&'}
config_file = 'config.json'

if os.path.isfile(config_file):
	with open(config_file) as f:
		config.update(json.load(f))

with open('config.json', 'w') as f:
	json.dump(config, f, indent='\t')

if 'discord_token' not in config:
	sys.exit('Discord token must be supplied in configuration')

if sys.version_info < (3, 5):
	sys.exit('Dozer requires Python 3.5 or higher to run. This is version %s.' % '.'.join(sys.version_info[:3]))

from . import Dozer # After version check

bot = Dozer(config)
bot.run()
