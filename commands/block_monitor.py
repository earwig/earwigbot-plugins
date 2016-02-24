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
from time import time

from earwigbot.commands import Command
from earwigbot.exceptions import APIError

class BlockMonitor(Command):
    """Monitors for on-wiki blocked users joining a particular channel."""
    name = "block_monitor"
    hooks = ["join", "part"]

    def setup(self):
        try:
            config = self.config.commands[self.name]
            self._monitor_chan = config["monitorChannel"]
            self._report_chan = config["reportChannel"]
        except KeyError:
            self._monitor_chan = self._report_chan = None
            self.logger.warn("Cannot use without being properly configured")
        self._last = None

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

        if self._last and self._last[0] == ip:
            if time() - self._last[1] < 60 * 5:
                self._last = (ip, time())
                return
        self._last = (ip, time())

        block = self._get_block_for_ip(ip)
        if not block:
            return

        msg = ("\x02[{note}]\x0F Joined user \x02{nick}\x0F is {type}blocked "
               "on-wiki ([[User:{user}]]) because: {reason}")
        self.say(self._report_chan, msg.format(nick=data.nick, **block))

        log = ("Reporting block ({note}): {nick} is [[User:{user}]], "
               "{type}blocked because: {reason}")
        self.logger.info(log.format(nick=data.nick, **block))

    def _get_block_for_ip(self, ip):
        """Return a dictionary of blockinfo for an IP."""
        site = self.bot.wiki.get_site()
        try:
            result = site.api_query(
                action="query", list="blocks|globalblocks", bkip=ip, bgip=ip,
                bklimit=1, bglimit=1, bkprop="user|reason|range",
                bgprop="address|reason|range")
        except APIError:
            return
        lblocks = result["query"]["blocks"]
        gblocks = result["query"]["globalblocks"]
        if not lblocks and not gblocks:
            return

        block = lblocks[0] if lblocks else gblocks[0]
        if block["rangestart"] != block["rangeend"]:
            block["type"] = "range"
        else:
            block["type"] = "IP-"
        if not lblocks:
            block["type"] = "globally " + block["type"]
            block["user"] = block["address"]

        if re.search(r"web[ _-]?host", block["reason"], re.IGNORECASE):
            block["note"] = "webhost warning"
        else:
            block["note"] = "alert"
        return block
