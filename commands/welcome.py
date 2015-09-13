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

from threading import Thread
from time import sleep, time

from earwigbot.commands import Command

class Welcome(Command):
    """Welcome people who enter certain channels."""
    name = "welcome"
    commands = ["welcome", "greet"]
    hooks = ["join", "part", "msg"]

    def setup(self):
        try:
            self.channels = self.config.commands[self.name]
        except KeyError:
            self.channels = {}
        self.disabled = []

        self._throttle = False
        self._last_join = 0
        self._pending = []

    def check(self, data):
        if data.is_command and data.command in self.commands:
            return True
        try:
            if data.line[1] != "JOIN" and data.line[1] != "PART":
                return False
        except IndexError:
            pass
        if data.chan in self.channels:
            return True
        return False

    def process(self, data):
        if data.is_command:
            self.process_command(data)
            return

        if data.line[1] == "PART":
            if (data.chan, data.nick) in self._pending:
                self._pending.remove((data.chan, data.nick))
            return

        this_join = time()
        if this_join - self._last_join < 5:
            self._throttle = True
        else:
            self._throttle = False
        self._last_join = this_join

        if data.chan in self.disabled:
            return
        if not data.host.startswith("gateway/web/"):
            return

        t_id = "welcome-{0}-{1}".format(data.chan.replace("#", ""), data.nick)
        thread = Thread(target=self._callback, name=t_id, args=(data,))
        thread.daemon = True
        thread.start()

    def _callback(self, data):
        """Internal callback function."""
        self._pending.append((data.chan, data.nick))
        sleep(2)

        if data.chan in self.disabled or self._throttle:
            return
        if (data.chan, data.nick) not in self._pending:
            return
        self.say(data.chan, self.channels[data.chan].format(nick=data.nick))

        try:
            self._pending.remove((data.chan, data.nick))
        except ValueError:
            pass  # Could be a race condition

    def process_command(self, data):
        """Handle this when it is an explicit command, not a channel join."""
        if data.args:
            if not self.config.irc["permissions"].is_admin(data):
                msg = "You must be a bot admin to use this command."
                self.reply(data, msg)
            elif data.arg[0] == "disable":
                if len(data.arg) < 2:
                    self.reply(data, "Which channel should I disable?")
                elif data.arg[1] in self.disabled:
                    msg = "Welcoming in \x02{0}\x0F is already disabled."
                    self.reply(data, msg.format(data.arg[1]))
                elif data.arg[1] not in self.channels:
                    msg = ("I'm not welcoming people in \x02{0}\x0F. "
                           "Only the bot owner can add new channels.")
                    self.reply(data, msg.format(data.arg[1]))
                else:
                    self.disabled.append(data.arg[1])
                    msg = ("Disabled welcoming in \x02{0}\x0F. Re-enable with "
                           "\x0306!welcome enable {0}\x0F.")
                    self.reply(data, msg.format(data.arg[1]))
            elif data.arg[0] == "enable":
                if len(data.arg) < 2:
                    self.reply(data, "Which channel should I enable?")
                elif data.arg[1] not in self.disabled:
                    msg = ("I don't have welcoming disabled in \x02{0}\x0F. "
                           "Only the bot owner can add new channels.")
                    self.reply(data, msg.format(data.arg[1]))
                else:
                    self.disabled.remove(data.arg[1])
                    msg = "Enabled welcoming in \x02{0}\x0F."
                    self.reply(data, msg.format(data.arg[1]))
            else:
                self.reply(data, "I don't understand that command.")
        else:
            msg = ("This command welcomes people who enter certain channels. "
                   "I am welcoming people in: {0}. A bot admin can disable me "
                   "with \x0306!welcome disable [channel]\x0F.")
            self.reply(data, msg.format(", ".join(self.channels.keys())))
