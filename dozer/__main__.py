import json
from . import Dozer

with open('config.json') as f:
	config = json.load(f)
	bot = Dozer(config)

bot.run()
