EarwigBot Plugins
=================

Additional IRC commands and bot tasks for
[EarwigBot](https://github.com/earwig/earwigbot). They are included separately
due to being outside of most peoples' use cases, or because they require
additional setup aside from the main bot. To install, place the command or task
file in its respective subdirectory in the bot's working directory (the same
one that contains its config file).

IRC Commands
------------

- **AFC-related commands** (*afc_pending*, *afc_report*, *afc_status*,
  *afc_submissions*): implements various services for
  [Articles for creation](http://en.wikipedia.org/wiki/WP:AFC). It has no
  dependencies, but `afc_report` requires the `afc_statistics` task plugin for
  parsing submissions. `afc_submissions` accepts a config option,
  `"ignoreList"`, a list of page titles to skip; it will try to use
  `afc_statistics`'s ignore list if none is defined.

- **geolocate**: implements an IP geolocator using
  [ipinfodb](http://ipinfodb.com/). Requires an API key stored in its config as
  `"apiKey"`, which should be stored encrypted if that option is enabled.

- **git**: allows the bot to carry out basic git maintenance functions, like
  pulling and checking out branches on repositories. A list of repo paths
  should be stored in its config as `"repos"`. Has one dependency,
  [GitPython](http://packages.python.org/GitPython), which can be installed
  with `pip install GitPython`.

- **praise**: adds a simple way for the bot respond to ad-hoc commands based on
  entries in `praise`'s config (in the `"praises"` dictionary). Its original
  intention was to implement silly "easter eggs" praising certain users; for
  example, `"!earwig"` would make the bot say "Earwig is the bestest Python
  programmer ever!". This would be implemented by having an entry in
  `"praises"` with the key `"earwig"` and the value
  `"Earwig is the bestest Python programmer ever!"`.

- **stars**: gets the number of stargazers for (i.e., people starring) a given
  [GitHub](https://github.com/) repository.

- **urbandictionary**: looks up terms on
  [Urban Dictionary](https://www.urbandictionary.com/). Separated from the main
  command list because these are often distasteful or unwanted.

- **weather**: gives current weather information for a location from
  [Weather Underground](http://www.wunderground.com/). Requires an API key
  stored in its config as `"apiKey"`, which should be stored encrypted if that
  option is enabled.

Bot Tasks
---------

- **afc_catdelink**: delinks mainspace categories (or templates, if necessary)
  in declined [AFC](http://en.wikipedia.org/wiki/WP:AFC) submissions.

- **afc_copyvios**: checks newly-edited AFC submissions for copyright
  violations using the bot's built-in copyvio checking support. Takes multiple
  config values, including connection info for a MySQL database to store
  processed pages and a cache (disabled by default; usable by the
  [toolserver interface](https://toolserver.org/~earwig/copyvios)). A script to
  create the database is in `tasks/schema/afc_copyvios.sql`.

- **afc_dailycats**: creates daily, monthly, and yearly categories for AFC.

- **afc_history**: generates charts about AFC submissions over time, including
  number of pending submissions throughout the project's history as well as
  counts for individual reviewers. Takes multiple config values, including
  MySQL database info. A script to create the database is in
  `tasks/schema/afc_history.sql`.

- **afc_statistics**: generates statistics for AFC on the current number of
  pending submissions and recently declined or accepted ones. Takes multiple
  config values, including MySQL database info. A script to create the database
  is in `tasks/schema/afc_statistics.sql`.

- **afc_undated**: periodically clears
  [Category:Undated AfC submissions](http://en.wikipedia.org/wiki/Category:Undated_AfC_submissions).

- **blp_tag**: adds `|blp=yes to` `{{WPB}}` or `{{WPBS}}` when it is used along
  with ``{{WP Biography}}``.

- **drn_clerkbot**: clerks the
  [dispute resolution noticeboard](http://en.wikipedia.org/wiki/WP:DRN),
  updating case statuses, building a chart, and notifying users. Takes multiple
  config values, including MySQL database info. A script to create the database
  is in `tasks/schema/drn_clerkbot.sql`.

- **image_display_resize**: resizes upscaled portraits in infoboxes.
