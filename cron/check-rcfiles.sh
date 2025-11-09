#! /bin/bash
#
# This script checks that the rcfiles are all up to date. It's designed to be
# run from cron.
#

cd ~/rcfiles || exit

LINE="------------------------------------------------------------------------------"

# Should we send an email about this cron run?
SENDEMAIL=0

DATE=`date -u +%Y%m%d%H%M%S`

# Create the output locations
OUTPUTDIR=~/rcfiles/tmp
if [ ! -d $OUTPUTDIR ]; then
	mkdir -p $OUTPUTDIR
fi
OUTPUTFILE=$OUTPUTDIR/cron.$DATE
touch $OUTPUTFILE

##########################################################################
# Output a head
echo >> $OUTPUTFILE
echo "Hi Tim," >> $OUTPUTFILE
echo >> $OUTPUTFILE
echo "rcfiles on $HOSTNAME has the following issues:" >> $OUTPUTFILE
echo >> $OUTPUTFILE

##########################################################################

##########################################################################
# Check if there is anything to commit
echo >> $OUTPUTFILE
echo "Checking to see if anything needs committing" >> $OUTPUTFILE
echo $LINE >> $OUTPUTFILE
##########################################################################

git status >> $OUTPUTFILE 2>&1
GITSTATUS_RETCODE=$?
# Git status failed !?
if [ $GITSTATUS_RETCODE -gt 0 ]; then
	SENDEMAIL=1
	echo "git status failed" >> $OUTPUTFILE
fi

GITDIRTY=`grep 'working directory clean' $OUTPUTFILE | wc -l`
# If we have don't have 1 line, then there are changes
if [ $GITDIRTY -ne 1 ]; then
	SENDEMAIL=1
fi

GITPUSH=`grep 'Your branch is ahead of' $OUTPUTFILE | wc -l`
# If we have one 1 line, then there are changes to push
if [ $GITPUSH -gt 0 ]; then
	SENDEMAIL=1
fi

# If the work directory is dirty or needs pushing, don't do anything more.
if [ "$GITDIRTY" -eq 1 ] && [ "$GITPUSH" -eq 0 ]; then
	##########################################################################
	# Check if there is anything to fetch
	echo >> $OUTPUTFILE
	echo "Fetching any new upstream commits" >> $OUTPUTFILE
	echo $LINE >> $OUTPUTFILE
	##########################################################################
	GITFETCH=`git fetch --all --tags 2>&1 | tee -a $OUTPUTFILE | wc -l`
	GITFETCH_RETCODE=$?
	# If we have more then 1 line, we actually fetched things
	if [ $GITFETCH -gt 1 ]; then
		SENDEMAIL=1
	fi
	# Git fetch failed.
	if [ $GITFETCH_RETCODE -gt 0 ]; then
		SENDEMAIL=1
		echo "git fetch failed" >> $OUTPUTFILE
	fi

	##########################################################################
	# Check if we can merge the upstream changes
	GITMERGE=`git merge '@{u}' --ff-only 2>&1 | tee -a $OUTPUTFILE | wc -l`
	GITMERGE_RETCODE=$?
	if [ $GITMERGE -ne 1 ]; then
		SENDEMAIL=1
	fi
	# Git merge failed fast-forward
	if [ $GITMERGE_RETCODE -gt 0 ]; then
		SENDEMAIL=1
		echo "git merge failed (fast-forward)" >> $OUTPUTFILE
	fi
fi


##########################################################################
# If we don't want to send email, then we should clean up.
if [ $SENDEMAIL -eq 0 ]; then
	rm $OUTPUTDIR/*
else
# Check if we have already sent an email - indicated by file left in $OUTPUTDIR
	if [ "$(ls "$OUTPUTDIR" | wc -l)" -gt 1 ]; then
		rm $OUTPUTFILE
	else
		# Send an email
		cat $OUTPUTFILE
	fi
fi
