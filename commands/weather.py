# -*- coding: utf-8  -*-
#
# Copyright (C) 2009-2013 Ben Kurtovic <ben.kurtovic@verizon.net>
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
from urllib import quote
from urllib2 import urlopen

from earwigbot.commands import Command

class Weather(Command):
    """Get a weather forecast (via http://www.wunderground.com/)."""
    name = "weather"
    commands = ["weather", "forecast", "temperature", "temp"]

    def setup(self):
        self.config.decrypt(self.config.commands, self.name, "apiKey")
        try:
            self.key = self.config.commands[self.name]["apiKey"]
        except KeyError:
            self.key = None
            addr = "http://wunderground.com/weather/api/"
            config = 'config.commands["{0}"]["apiKey"]'.format(self.name)
            log = "Cannot use without an API key from {0} stored as {1}"
            self.logger.warn(log.format(addr, config))

    def process(self, data):
        if not self.key:
            addr = "http://wunderground.com/weather/api/"
            config = 'config.commands["{0}"]["apiKey"]'.format(self.name)
            msg = "I need an API key from {0} stored as \x0303{1}\x0F."
            log = "Need an API key from {0} stored as {1}"
            self.reply(data, msg.format(addr, config))
            self.logger.error(log.format(addr, config))
            return
        if not data.args:
            self.reply(data, "Where do you want the weather of?")
            return

        url = "http://api.wunderground.com/api/{0}/conditions/q/{1}.json"
        location = quote("_".join(data.args), safe="")
        query = urlopen(url.format(self.key, location)).read()
        res = loads(query)

        if "error" in res:
            try:
                desc = res["error"]["description"]
                desc[0] = desc[0].upper()
                if desc[-1] not in (".", "!", "?"):
                    desc += "."
            except (KeyError, IndexError):
                desc = "An unknown error occurred."
            self.reply(data, desc)

        elif "current_observation" in res:
            msg = self.format_weather(res["current_observation"])
            self.reply(data, msg)

        elif "results" in res["response"]:
            results = []
            for place in res["response"]["results"]:
                extra = place["state" if place["state"] else "country_iso3166"]
                results.append("{0}, {1}".format(place["city"], extra))
            msg = "Did you mean: {0}?".format("; ".join(results))
            self.reply(data, msg)

        else:
            self.reply(data, "An unknown error occurred.")

    def format_weather(self, data):
        """Format the weather (as dict *data*) to be sent through IRC."""
        place = data["display_location"]["full"]
        icon = self.get_icon(data["icon"])
        weather = data["weather"]
        temp_f, temp_c = data["temp_f"], data["temp_c"]
        humidity = data["relative_humidity"]
        wind = "{0} {1} mph".format(data["wind_dir"], data["wind_mph"])
        if int(data["wind_gust_mph"]) > int(data["wind_mph"]):
            wind += " ({0} mph gusts)".format(data["wind_gust_mph"])
        precip_today = data["precip_today_in"]
        precip_hour = data["precip_1hr_in"]

        msg = "\x02{0}\x0F: {1} {2}; {3}°F ({4}°C); {5} humidity; wind {6}; "
        msg += "{7}″ precipitation today ({8}″ past hour)"
        msg = msg.format(place, icon, weather, temp_f, temp_c, humidity, wind,
                         precip_today, precip_hour)
        return msg

    def get_icon(self, condition):
        """Return a unicode icon to describe the given weather condition."""
        icons = {
            "chanceflurries" : "☃",
            "chancerain" : "☂",
            "chancesleet" : "☃",
            "chancesnow" : "☃",
            "chancetstorms" : "☂",
            "clear" : "☀",
            "cloudy" : "☁",
            "flurries" : "☃",
            "fog" : "☁",
            "hazy" : "☁",
            "mostlycloudy" : "☁",
            "mostlysunny" : "☀",
            "partlycloudy" : "☁",
            "partlysunny" : "☀",
            "rain" : "☂",
            "sleet" : "☃",
            "snow" : "☃",
            "sunny" : "☀",
            "tstorms" : "☂",
        }
        try:
            return icons[condition]
        except KeyError:
            return "?"
