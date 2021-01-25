# -*- coding: utf-8  -*-
#
# Copyright (C) 2021 Ben Kurtovic <ben.kurtovic@gmail.com>
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

import base64
import cPickle as pickle
import re

from earwigbot.commands import Command
from earwigbot.config.permissions import User

class PartWhen(Command):
    """Ask the bot to part the channel when a condition is met."""
    name = "partwhen"
    commands = ["partwhen", "unpartwhen"]
    hooks = ["join", "msg"]

    def setup(self):
        self._conds = self._load_conditions()

    def check(self, data):
        if data.is_command and data.command in self.commands:
            return True
        try:
            if data.line[1] == "JOIN":
                if data.chan in self._conds and "join" in self._conds[data.chan]:
                    return True
        except IndexError:
            pass
        return False

    def process(self, data):
        if data.line[1] == "JOIN":
            self._handle_join(data)
            return

        if not self.config.irc["permissions"].is_admin(data):
            self.reply(data, "You must be a bot admin to use this command.")
            return

        channel = data.chan
        args = data.args
        if args and args[0].startswith("#"):
            # "!partwhen #channel <event> <args>..."
            channel = args[0]
            args = args[1:]

        if data.command == "unpartwhen":
            if self._conds.get(channel):
                del self._conds[channel]
                self._save_conditions()
                self.reply(data, "Cleared part conditions for {0}.".format(
                    "this channel" if channel == data.chan else channel))
            else:
                self.reply(data, "No part conditions set.")
            return

        if not args:
            conds = self._conds.get(channel, {})
            existing = "; ".join("{0} {1}".format(cond, ", ".join(str(user) for user in users))
                                 for cond, users in conds.iteritems())
            if existing:
                status = "Current part conditions: {0}.".format(existing)
            else:
                status = "No part conditions set for {0}.".format(
                    "this channel" if channel == data.chan else channel)
            self.reply(data, "{0} Usage: !{1} [<channel>] <event> <args>...".format(
                status, data.command))
            return

        event = args[0]
        args = args[1:]
        if event == "join":
            if not args:
                self.reply(data, "Join event requires an argument for the user joining, "
                                 "in nick!ident@host syntax.")
                return
            cond = args[0]
            match = re.match(r"(.*?)!(.*?)@(.*?)$", cond)
            if not match:
                self.reply(data, "User join pattern is invalid; should use "
                                 "nick!ident@host syntax.")
                return
            conds = self._conds.setdefault(channel, {}).setdefault("join", [])
            conds.append(User(match.group(1), match.group(2), match.group(3)))
            self._save_conditions()
            self.reply(data, "Okay, I will leave {0} when {1} joins.".format(
                "the channel" if channel == data.chan else channel, cond))
        else:
            self.reply(data, "Unknown event: {0} (valid events: join).".format(event))

    def _handle_join(self, data):
        user = User(data.nick, data.ident, data.host)
        conds = self._conds.get(data.chan, {}).get("join", {})
        for cond in conds:
            if user in cond:
                self.logger.info("Parting {0} because {1} met join condition {2}".format(
                    data.chan, str(user), str(cond)))
                self.part(data.chan, "Requested to leave when {0} joined".format(data.nick))
                break

    def _load_conditions(self):
        permdb = self.config.irc["permissions"]
        try:
            raw = permdb.get_attr("command:partwhen", "data")
        except KeyError:
            return {}
        return pickle.loads(base64.b64decode(raw))

    def _save_conditions(self):
        permdb = self.config.irc["permissions"]
        raw = base64.b64encode(pickle.dumps(self._conds, pickle.HIGHEST_PROTOCOL))
        permdb.set_attr("command:partwhen", "data", raw)
