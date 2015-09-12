# -*- coding: utf-8  -*-
#
# Copyright (C) 2015 Ben Kurtovic <ben.kurtovic@gmail.com>
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
    API_REPOS = "https://api.github.com/repos/{repo}"
    API_USERS = "https://api.github.com/users/{user}/repos"
    EXAMPLE = "!stars earwig/earwigbot"

    def process(self, data):
        if not data.args:
            msg = "Which GitHub repository or user should I look up? Example: \x0306{0}\x0F."
            self.reply(data, msg.format(self.EXAMPLE))
            return

        arg = data.args[0]
        if "/" in arg:
            self.handle_repo(data, arg)
        else:
            self.handle_user(data, arg)

    def handle_repo(self, data, arg):
        """Handle !stars <user>/<repo>."""
        repo = self.get_repo(arg)
        if repo is None:
            self.reply(data, "Repository not found. Is it private?")
            return

        count = int(repo["stargazers_count"])
        plural = "" if count == 1 else "s"

        msg = "\x0303{0}\x0F has \x02{1}\x0F stargazer{2}: {3}"
        self.reply(data, msg.format(
            repo["full_name"], count, plural, repo["html_url"]))

    def handle_user(self, data, arg):
        """Handle !stars <user>."""
        repos = self.get_user_repos(arg)
        if repos is None:
            self.reply(data, "User not found.")
            return

        star_count = sum(repo["stargazers_count"] for repo in repos)
        star_plural = "" if star_count == 1 else "s"
        repo_plural = "" if len(repos) == 1 else "s"
        if len(repos) > 0:
            name = repos[0]["owner"]["login"]
            url = repos[0]["owner"]["html_url"]
        else:
            name = arg
            url = "https://github.com/{0}".format(name)

        msg = "\x0303{0}\x0F has \x02{1}\x0F stargazer{2} across {3} repo{4}: {5}"
        self.reply(data, msg.format(
            name, star_count, star_plural, len(repos), repo_plural, url))

    def get_repo(self, repo):
        """Return the API JSON dump for a given repository.

        Return None if the repo doesn't exist or is private.
        """
        try:
            query = urlopen(self.API_REPOS.format(repo=repo)).read()
        except HTTPError:
            return None
        res = loads(query)
        if res and "id" in res and not res["private"]:
            return res
        return None

    def get_user_repos(self, user):
        """Return the API JSON dump for a given user's repositories.

        Return None if the user doesn't exist.
        """
        try:
            query = urlopen(self.API_USERS.format(user=user)).read()
        except HTTPError:
            return None
        res = loads(query)
        if res and isinstance(res, list):
            return res
        return None
