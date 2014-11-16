# -*- coding: utf-8  -*-
#
# Copyright (C) 2009-2014 Ben Kurtovic <ben.kurtovic@gmail.com>
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

from datetime import datetime
from json import loads
from urllib import quote
from urllib2 import urlopen

from earwigbot.commands import Command

class Weather(Command):
    """Get a weather forecast (via http://www.wunderground.com/)."""
    name = "weather"
    commands = ["weather", "weat", "forecast", "temperature", "temp"]

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

        permdb = self.config.irc["permissions"]
        if not data.args:
            if permdb.has_attr(data.host, "weather"):
                location = permdb.get_attr(data.host, "weather")
            else:
                msg = " ".join(("Where do you want the weather of? You can",
                                "set a default with '!{0} default City,",
                                "State' (or 'City, Country' if non-US)."))
                self.reply(data, msg.format(data.command))
                return
        elif data.args[0] == "default":
            if data.args[1:]:
                value = " ".join(data.args[1:])
                permdb.set_attr(data.host, "weather", value)
                msg = "\x0302{0}\x0F's default set to \x02{1}\x0F."
                self.reply(data, msg.format(data.host, value))
            else:
                if permdb.has_attr(data.host, "weather"):
                    value = permdb.get_attr(data.host, "weather")
                    msg = "\x0302{0}\x0F's default is \x02{1}\x0F."
                    self.reply(data, msg.format(data.host, value))
                else:
                    self.reply(data, "I need a value to set as your default.")
            return
        else:
            location = " ".join(data.args)

        url = "http://api.wunderground.com/api/{0}/conditions/astronomy/q/{1}.json"
        location = quote(location, safe="")
        query = urlopen(url.format(self.key, location)).read()
        res = loads(query)

        if "error" in res["response"]:
            try:
                desc = res["response"]["error"]["description"]
                desc = desc[0].upper() + desc[1:]
                if desc[-1] not in (".", "!", "?"):
                    desc += "."
            except (KeyError, IndexError):
                desc = "An unknown error occurred."
            self.reply(data, desc)
        elif "current_observation" in res:
            msg = self.format_weather(res)
            self.reply(data, msg)
        elif "results" in res["response"]:
            msg = self.format_ambiguous_result(res)
            self.reply(data, msg)
        else:
            self.reply(data, "An unknown error occurred.")

    def format_weather(self, res):
        """Format the weather (as dict *data*) to be sent through IRC."""
        data = res["current_observation"]
        place = data["display_location"]["full"]
        icon = self.get_icon(data["icon"], data["local_time_rfc822"],
                             res["sun_phase"])
        weather = data["weather"]
        temp_f, temp_c = data["temp_f"], data["temp_c"]
        humidity = data["relative_humidity"]
        wind_dir = data["wind_dir"]
        if wind_dir in ("North", "South", "East", "West"):
            wind_dir = wind_dir.lower()
        wind = "{0} {1} mph".format(wind_dir, data["wind_mph"])
        if float(data["wind_gust_mph"]) > float(data["wind_mph"]):
            wind += " ({0} mph gusts)".format(data["wind_gust_mph"])

        msg = "\x02{0}\x0F: {1} {2}; {3}°F ({4}°C); {5} humidity; wind {6}"
        msg = msg.format(place, icon, weather, temp_f, temp_c, humidity, wind)
        if data["precip_today_in"] and float(data["precip_today_in"]) > 0:
            msg += "; {0}″ precipitation today".format(data["precip_today_in"])
            if data["precip_1hr_in"] and float(data["precip_1hr_in"]) > 0:
                msg += " ({0}″ past hour)".format(data["precip_1hr_in"])
        return msg

    def get_icon(self, condition, local_time, sun_phase):
        """Return a unicode icon to describe the given weather condition."""
        icons = {
            "chanceflurries" : "☃",
            "chancerain" : "☂",
            "chancesleet" : "☃",
            "chancesnow" : "☃",
            "chancetstorms" : "☂",
            "clear" : "☽☀",
            "cloudy" : "☁",
            "flurries" : "☃",
            "fog" : "☁",
            "hazy" : "☁",
            "mostlycloudy" : "☁",
            "mostlysunny" : "☽☀",
            "partlycloudy" : "☁",
            "partlysunny" : "☽☀",
            "rain" : "☂",
            "sleet" : "☃",
            "snow" : "☃",
            "sunny" : "☽☀",
            "tstorms" : "☂",
        }
        try:
            icon = icons[condition]
            if len(icon) == 2:
                lt_no_tz = local_time.rsplit(" ", 1)[0]
                dt = datetime.strptime(lt_no_tz, "%a, %d %b %Y %H:%M:%S")
                srise = datetime(year=dt.year, month=dt.month, day=dt.day,
                                 hour=int(sun_phase["sunrise"]["hour"]),
                                 minute=int(sun_phase["sunrise"]["minute"]))
                sset = datetime(year=dt.year, month=dt.month, day=dt.day,
                                hour=int(sun_phase["sunset"]["hour"]),
                                minute=int(sun_phase["sunset"]["minute"]))
                return icon[int(srise < dt < sset)]
            return icon
        except KeyError:
            return "?"

    def format_ambiguous_result(self, res):
        """Format a message when there are multiple possible results."""
        results = []
        for place in res["response"]["results"]:
            extra = place["state" if place["state"] else "country"]
            results.append("{0}, {1}".format(place["city"], extra))
        if len(results) > 21:
            extra = len(results) - 20
            res = "; ".join(results[:20])
            return "Did you mean: {0}... ({1} others)?".format(res, extra)
        return "Did you mean: {0}?".format("; ".join(results))
