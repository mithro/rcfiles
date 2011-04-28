#! /bin/sh

# Script which does incremental backup of my laptop.

#rsync -avz -e 'ssh -C -c blowfish -ax' --delete-after \
#rsync -avz -e 'ssh -C -c blowfish -ax' --delete-after \
#	--links --hard-links \
#	--progress --stats \
#	\
#	--exclude=Spam* \
#	--exclude=vmware \
#	--exclude=videos \
#	--exclude=astc \
#	--exclude=.Trash \
#	--exclude=.cache \
#	--exclude=cache \
#	--exclude=Cache \
#	--exclude=.thumbnails \
#	--exclude=.wine \
#	--exclude=wxPython \
#	\
#	/home/tim tim@10.1.1.65:/mnt/backup/laptop/vaio

sudo umount /dev/$1

export NOMOUNT=0
sudo mount /dev/$1 /mnt/backup || export NOMOUNT=1

if [ $NOMOUNT = 1 ]; then
	echo "Unable to mount disk"
	exit
else
	echo "Mount okay"
fi

DEST=/mnt/backup/backups
BACKUP=`date +%Y%m%d`
LASTDIR=`ls $DEST | tail -1`

echo "$DEST/$BACKUP (using $DEST/$LASTDIR)"

rsync -av --delete-after \
		--links --hard-links \
		--progress --stats \
		--exclude=\*.avi \
		--exclude=\*.divx \
		\
		--link-dest=$DEST/$LASTDIR \
		/home/tim $DEST/$BACKUP

sudo umount /dev/$1
