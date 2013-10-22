# -*- coding: utf-8  -*-
#
# Copyright (C) 2009-2013 Ben Kurtovic <ben.kurtovic@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from json import loads
from socket import (AF_INET, AF_INET6, error as socket_error, gethostbyname,
                    inet_pton)
from urllib2 import urlopen

from earwigbot.commands import Command

class Geolocate(Command):
    """Geolocate an IP address (via http://ipinfodb.com/)."""
    name = "geolocate"
    commands = ["geolocate", "locate", "geo", "ip"]

    def setup(self):
        self.config.decrypt(self.config.commands, self.name, "apiKey")
        try:
            self.key = self.config.commands[self.name]["apiKey"]
        except KeyError:
            self.key = None
            log = 'Cannot use without an API key for http://ipinfodb.com/ stored as config.commands["{0}"]["apiKey"]'
            self.logger.warn(log.format(self.name))

    def process(self, data):
        if not self.key:
            msg = 'I need an API key for http://ipinfodb.com/ stored as \x0303config.commands["{0}"]["apiKey"]\x0F.'
            log = 'Need an API key for http://ipinfodb.com/ stored as config.commands["{0}"]["apiKey"]'
            self.reply(data, msg.format(self.name))
            self.logger.error(log.format(self.name))
            return

        if data.args:
            address = data.args[0]
        else:
            try:
                address = gethostbyname(data.host)
            except socket_error:
                msg = "Your hostname, \x0302{0}\x0F, is not an IP address!"
                self.reply(data, msg.format(data.host))
                return
        if not self.is_ip(address):
            msg = "\x0302{0}\x0F is not an IP address!"
            self.reply(data, msg.format(address))
            return

        url = "http://api.ipinfodb.com/v3/ip-city/?key={0}&ip={1}&format=json"
        query = urlopen(url.format(self.key, address)).read()
        res = loads(query)

        country = res["countryName"].title()
        region = res["regionName"].title()
        city = res["cityName"].title()
        latitude = res["latitude"]
        longitude = res["longitude"]
        utcoffset = res["timeZone"]
        if not country and not region and not city:
            self.reply(data, "IP \x0302{0}\x0F not found.".format(address))
            return
        if country == "-" and region == "-" and city == "-":
            self.reply(data, "IP \x0302{0}\x0F is reserved.".format(address))
            return

        msg = "{0}, {1}, {2} ({3}, {4}), UTC {5}"
        geo = msg.format(country, region, city, latitude, longitude, utcoffset)
        self.reply(data, geo)

    def is_ip(self, address):
        """Return ``True`` if the input is an IP address, else ``False``.

        This tests for IPv4 and IPv6 using :py:func:`socket.inet_pton`.
        """
        try:
            inet_pton(AF_INET, address)
        except socket_error:
            try:
                inet_pton(AF_INET6, address)
            except socket_error:
                return False
        return True
