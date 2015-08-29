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

from json import loads
from urllib2 import urlopen, HTTPError

from earwigbot.commands import Command

class Stars(Command):
    """Get the number of stargazers for a given GitHub repository."""
    name = "stars"
    commands = ["stars", "stargazers"]
    API_URL = "https://api.github.com/repos/{repo}"
    EXAMPLE = "!stars earwig/earwigbot"

    def process(self, data):
        if not data.args:
            msg = "Which repository should I look up? Example: \x0306{0}\x0F."
            self.reply(data, msg.format(self.EXAMPLE))
            return

        repo = data.args[0]
        info = self.get_repo(repo)
        if info is None:
            self.reply(data, "Repository not found. Is it private?")
        else:
            msg = "\x0303{0}\x0F has \x02{1}\x0F stargazers: {2}"
            self.reply(data, msg.format(
                info["full_name"], info["stargazers_count"], info["html_url"]))

    def get_repo(self, repo):
        """Return the API JSON dump for a given repository.

        Return None if the repo doesn't exist or is private.
        """
        try:
            query = urlopen(self.API_URL.format(repo=repo)).read()
        except HTTPError:
            return None
        res = loads(query)
        if res and "id" in res and not res["private"]:
            return res
        return None
