"""Provides access to The Orange Alliance for FTC data."""

import json
from asyncio import sleep
from datetime import datetime
from urllib.parse import urljoin

import aiohttp
import async_timeout


class TOAParser:
    """
    A class to make async requests to The Orange Alliance.
    """

    def __init__(self, api_key, aiohttp_session, base_url="https://theorangealliance.org/apiv2/", app_name="Dozer",
                 ratelimit=True):
        self.last_req = datetime.now()
        self.ratelimit = ratelimit
        self.base = base_url
        self.http = aiohttp_session
        self.headers = {
            "X-Application-Origin": app_name,
            "X-TOA-Key": api_key
        }

    async def req(self, endpoint):
        """Make an async request at the specified endpoint, waiting to let the ratelimit cool off."""
        if self.ratelimit:
            # this will delay a request to avoid the ratelimit
            now = datetime.now()
            diff = (now - self.last_req).total_seconds()
            self.last_req = now
            if diff < 2.2:  # have a 200 ms fudge factor
                await sleep(2.2 - diff)
        tries = 0
        while True:
            try:
                async with async_timeout.timeout(5) as _, self.http.get(urljoin(self.base, endpoint),
                                                                        headers=self.headers) as response:
                    res = TOAResponse()
                    # it seems sometimes toa forgets to return data as application/json and not text/html
                    data = json.loads(await response.text())
                    if data:
                        res._update(data[0])
                    else:
                        res.error = True
                    return res
            except aiohttp.ClientError:
                tries += 1
                if tries > 3:
                    raise


class TOAResponse:
    """Represents a response from the TOA API."""
    def __init__(self):
        self.error = False

    def _update(self, v):
        self.__dict__.update(v)
