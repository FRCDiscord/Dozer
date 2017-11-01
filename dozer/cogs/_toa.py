import aiohttp
import async_timeout
from urllib.parse import urljoin

class TOAParser(object):
	"""
	A class to make async requests to The Orange Alliance.
	"""
	def __init__(self, api_key, base_url="https://beta.theorangealliance.org/api/", app_name="Dozer"):
		self.base = base_url
		self.headers = {
			"X-Application-Origin": app_name,
			"X-TOA-Key": api_key
		}

	async def req(self, endpoint):
		"""Make an async request at the specified endpoint."""
		async with aiohttp.ClientSession() as session:
			with async_timeout.timeout(5):
				async with session.get(urljoin(self.base, endpoint), headers=self.headers) as response:
					res = TOAResponse()
					res._update((await response.json())[0])
					return res

class TOAResponse(object):
	def __init__(self):
		self.error = None
	def _update(self, v):
		self.__dict__.update(v)
