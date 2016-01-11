# -*- coding: utf-8  -*-
#
# Copyright (C) 2016 Ben Kurtovic <ben.kurtovic@gmail.com>
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

import re

from earwigbot.commands import Command
from earwigbot.exceptions import APIError

class LTAMonitor(Command):
    """Monitors for LTAs. No further information is available."""
    name = "lta_monitor"
    hooks = ["join", "part"]

    def setup(self):
        try:
            config = self.config.commands[self.name]
            self._monitor_chan = config["monitorChannel"]
            self._report_chan = config["reportChannel"]
        except KeyError:
            self._monitor_chan = self._report_chan = None
            self.logger.warn("Cannot use without being properly configured")
        self._recent = []
        self._recent_max = 10

    def check(self, data):
        return (self._monitor_chan and self._report_chan and
                data.chan == self._monitor_chan)

    def process(self, data):
        if not data.host.startswith("gateway/web/"):
            return
        match = re.search(r"/ip\.(.*?)$", data.host)
        if not match:
            return
        ip = match.group(1)
        if ip in self._recent:
            return
        self._recent.append(ip)
        if len(self._recent) > self._recent_max:
            self._recent.pop(0)

        site = self.bot.wiki.get_site()
        try:
            result = site.api_query(action="query", list="blocks", bkip=ip,
                                    bklimit=1, bkprop="user|reason|range")
        except APIError:
            return
        blocks = result["query"]["blocks"]
        if not blocks:
            return
        block = blocks[0]

        if re.search(r"web[ _-]?host", block["reason"], re.IGNORECASE):
            block["note"] = "webhost warning"
        else:
            block["note"] = "alert"
        if block["rangestart"] != block["rangeend"]:
            block["type"] = "range"
        else:
            block["type"] = "IP-"

        msg = ("\x02[{note}]\x0F Joined user \x02{nick}\x0F is {type}blocked "
               "on-wiki ([[User:{user}]]) because: {reason}")
        self.say(self._report_chan, msg.format(nick=data.nick, **block))

        log = ("Reporting block ({note}): {nick} is [[User:{user}]], "
               "{type}blocked because: {reason}")
        self.logger.info(log.format(nick=data.nick, **block))
