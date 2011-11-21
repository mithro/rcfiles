#! /usr/bin/python

import subprocess
import re
import getpass
import os
import progressbar
import urllib

import ConfigParser

import gdata.photos.service
import gdata.media
import gdata.geo

config = ConfigParser.ConfigParser()
config.read([os.path.expanduser('~/.picasa.ini')])

username = config.get('login', 'username')

gd_client = gdata.photos.service.PhotosService()
gd_client.email = "%s@gmail.com" % username
gd_client.password = config.get('login', 'password')
gd_client.source = 'backup-picasa'
gd_client.ProgrammaticLogin()

albums = gd_client.GetUserFeed(user=username)

widgets = [progressbar.Percentage(), ' ', progressbar.Bar(), ' ', progressbar.ETA(), ' ', progressbar.FileTransferSpeed()]

def make_download_url(url):
  """Makes the given URL for a picasa image point to the download."""
  return url[:url.rfind('/')+1]+'d'+url[url.rfind('/'):]

for album in albums.entry:
	name = album.title.text
	localdir = re.sub('[^a-z0-9-_]', '.', name.lower().replace(" - ", "-").replace(', ', '-').replace(' & ', '-').replace(" ", "_"))
	print name, localdir
	if not os.path.exists(localdir):
		os.mkdir(localdir)

	photos = gd_client.GetFeed(
		'/data/feed/api/user/%s/albumid/%s' % (username, album.gphoto_id.text))
	for photo in photos.entry:
		ext = os.path.splitext(photo.title.text)[-1].upper()
		if ext == ".JPEG":
			ext = ".JPG"
		if not ext:
			ext = ".UNK"

		fileid = "%s-%s%s" % (photo.gphoto_id.text, photo.version.text, ext)
		filesize = int(photo.size)

		path = os.path.join(localdir, fileid)
		if not os.path.exists(path) or os.stat(path).st_size != filesize:
			url = make_download_url(photo.content.src)
			if not ext == ".JPG":
				print "Skipping", path, filesize, url
				continue

			print "Downloading", path, filesize, url

			pbar = progressbar.ProgressBar(maxval=filesize, widgets=widgets)
			pbar.start()
			def reporthook(a,b,c):
				assert c == filesize, "%s != %s" % (c, filesize)
				pbar.update(min(a*b, c))

			urllib.urlretrieve(url, reporthook=reporthook, filename=path)
			pbar.finish()
