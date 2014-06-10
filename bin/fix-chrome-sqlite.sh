#!/bin/sh

# This script fixes the problem where Chrome will crash and leave it's SQLite3
# databases (such as your login details) in the locked state.
#
# You'll get errors like
#   [18983:18983:627464845107:ERROR:profile_impl.cc(1054)] Could not initialize login database.
# and if you run sqlite3 on the DB you'll get
#   $ sqlite3 db
#   > .tables
#   Error: database is locked

find -type f -exec file \{\} \; | grep SQLite | sed -e's/: SQLite.*//' | while read db; do
	sqlite3 "$db" .tables 2>&1 | grep -i lock > /dev/null 2>&1 && export LOCKED='locked' || export LOCKED='unlocked'
	echo $db is $LOCKED
	if [ x$LOCKED == xlocked ]; then
		cp "$db" "$db.tmp"
		mv "$db.tmp" "$db"
		sqlite3 "$db" .tables 2>&1 | grep -i lock > /dev/null 2>&1 && export LOCKED='locked' || export LOCKED='unlocked'
		echo "    " is now $LOCKED
	fi
done
