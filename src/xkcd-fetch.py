#!/usr/bin/python

from urllib import urlretrieve
import re
import argparse
from time import sleep
import os
import sys
import codecs
import htmlentitydefs
import signal

# doesn't pause the first time it is called, pauses for a set time on each subsequent call
def sleep_if_necessary():
	global first_cache_miss
	if not(first_cache_miss):
		sleep(args.sleep_time)
	first_cache_miss = False

# replaces ugly things like &#33; with !
def remove_escapes(string):
	def remove_one(match):
		ref = match.group(0)
		if ref[:2] == "&#":
			if ref[:3] == "&#x":
				return unichr(int(ref[3:-1], 16))
			else:
				return unichr(int(ref[2:-1]))
		else:
			ref = unichr(htmlentitydefs.name2codepoint[ref[1:-1]])
		return ref
	return re.sub("&#?\w+;", remove_one, string)

# a class for holding comics
#  number      - the comic number
#  comic_title - the title of the comic
#  image_name  - the name of the image
#  title_text  - the title (mouseover) text
#  date        - the date of the comic (stored as a string)
#  transcript  - the transcript, if available
class Comic:
	# adds some lines to the end of a list of lines of output, representing the comic, in a form that can be read by read_comic()
	def write_comic(self, lines):
		lines.append(repr(self.number))
		lines.append(self.comic_title)
		lines.append(self.image_name)
		lines.append(self.title_text)
		lines.append(self.date)
		lines.append('<transcript>')
		lines.append(self.transcript)
		lines.append('</transcript>')
		lines.append('')

# takes a list of lines read from the comic data file, pops some off the front, and returns a Comic object.
def read_comic(lines):
	comic = Comic()
	comic.number = int(lines.pop(0))
	comic.comic_title = lines.pop(0).rstrip()
	comic.image_name = lines.pop(0).rstrip()
	comic.title_text = lines.pop(0).rstrip()
	comic.date = lines.pop(0).rstrip()
	assert '<transcript>' == lines.pop(0).rstrip()

	line = lines.pop(0).rstrip()
	comic.transcript = ''
	while line != '</transcript>':
		comic.transcript = comic.transcript + '\n' + line
		line = lines.pop(0).rstrip()
	comic.transcript = comic.transcript[1:] # strip the leading \n

	lines.pop(0)
	if os.path.exists(cache_path + '/' + comic.image_name):
		return comic
	else:
		return None

# downloads the image, title text, and transcript for the specified comic, and stores the data in the cache.
def download_comic(comics, comic_number):
	sleep_if_necessary()

	if not args.quiet:
		sys.stderr.write('Downloading comic ' + repr(comic_number) + '\n')

	url = 'http://www.xkcd.com'
	url = url + '/' + repr(comic_number)

	scratch_filename = cache_path + '/raw.html'
	urlretrieve(url, scratch_filename)
	raw = codecs.open(scratch_filename, 'r', 'utf-8')
	raw_html = raw.read()
	raw.close()
	os.remove(scratch_filename)

	comic_line_match = re.search(comic_line, raw_html)
	permalink_line_match = re.search(permalink_line, raw_html)
	transcript_line_match = re.search(transcript_line, raw_html)

	if not(comic_line_match) or not(permalink_line_match):
		return None
	
	assert comic_number == int(permalink_line_match.group(1))

	comics[comic_number].image_name = comic_line_match.group(1)
	comics[comic_number].title_text = remove_escapes(comic_line_match.group(2))

	if transcript_line_match:
		comics[comic_number].transcript = remove_escapes(transcript_line_match.group(1))

	image_path = cache_path + '/' + comics[comic_number].image_name
	if not os.path.exists(image_path):
		urlretrieve('http://imgs.xkcd.com/comics/' + comics[comic_number].image_name, image_path)

	assert os.path.exists(image_path)

# reads the cache from the comic data file into memory
def read_cache():
	comic_data_file = codecs.open(comic_data_path, 'r', 'utf-8')
	comic_data_lines = comic_data_file.readlines()
	comic_data_file.close()

	comics = {}

	while len(comic_data_lines) > 0:
		comic = read_comic(comic_data_lines)
		if comic:
			comics[comic.number] = comic

	return comics

# writes the cache from memory into the comic data file
def write_cache(comics):
	comic_data_lines = []
	for num in sorted(comics.keys()):
		comics[num].write_comic(comic_data_lines)

	comic_data_file = codecs.open(comic_data_path, 'w', 'utf-8')
	for line in comic_data_lines:
		comic_data_file.write(line + '\n')
	comic_data_file.close()

# fetch the comic from the cache, or downloads it in the case of a cache miss.
def fetch(comics, comic_number):
	if not(comic_number in comics):
		download_archive(comics)
		if not(comic_number in comics):
			return None
	if comics[comic_number].image_name == '':
		download_comic(comics, comic_number)
	return comics[comic_number]

# downloads the comic list, to learn about any new comics
def download_archive(comics):
	sleep_if_necessary()

	if not args.quiet:
		sys.stderr.write('Downloading comic list\n')

	url = 'http://www.xkcd.com/archive'

	scratch_filename = cache_path + '/raw.html'
	urlretrieve(url, scratch_filename)
	raw = codecs.open(scratch_filename, 'r', 'utf-8')
	raw_html = raw.read()
	raw.close()
	os.remove(scratch_filename)

	while True:
		archive_line_match = re.search(archive_line, raw_html)

		if not(archive_line_match):
			break

		num = int(archive_line_match.group(1))
		if not(num in comics.keys()):
			comics[num] = Comic()
			comics[num].number = num
			comics[num].date = archive_line_match.group(2)
			comics[num].comic_title = archive_line_match.group(3)
			comics[num].image_name = ''
			comics[num].title_text = ''
			comics[num].transcript = ''

		raw_html = raw_html[archive_line_match.end():]

if __name__ == "__main__":
	# set up command line arguments
	parser = argparse.ArgumentParser(description = 'Downloads, caches, and returns xkcd comics')
	parser.add_argument('-a', '--cache-all',
			    action = 'store_true',
			    help = 'Make sure that all the comics are downloaded into the cache.')
	parser.add_argument('-q', '--quiet',
			    action = 'store_true',
			    help = 'Suppress download status output on standard error.')
	parser.add_argument('-s', '--sleep-time',
			    metavar = 'TIME',
			    default = 1.0,
			    type = float,
			    help = 'Time (in seconds) to sleep between comic downloads in order to respect the server. Defaults to 1.0 seconds.')
	parser.add_argument('comic_nums',
			    metavar = 'N',
			    type = int,
			    nargs = '*',
			    help = 'Comic number to fetch. Defaults to the most recent comic.')
	args = parser.parse_args()

	# some handy paths
	rs_root = os.getenv('RED_SPIDER_ROOT','.')

	work_path = rs_root + '/work'
	cache_path = work_path + '/xkcd-fetch'
	comic_data_path = cache_path + '/comic-data.txt'

	# needed by sleep_if_necessary()
	first_cache_miss = True

	# handle SIGINT gracefully
	sigint = False
	def sigint_handler(signal, frame):
		sys.stderr.write('Received SIGINT, stopping and cleaning up.\n')
		global sigint
		sigint = True
	signal.signal(signal.SIGINT, sigint_handler)

	# if files don't exist, create them
	if not os.path.exists(work_path):
		os.mkdir(work_path)
	if not os.path.exists(cache_path):
		os.mkdir(cache_path)
	if not os.path.exists(comic_data_path):
		comic_data_file = codecs.open(comic_data_path, 'w', 'utf-8')
		comic_data_file.write('')
		comic_data_file.close()

	# handy regexes
	comic_line = re.compile('^[^\n]*<img src="http://imgs\.xkcd\.com/comics/(\S*)" title="([^\n]*)" alt="([^\n]*)" />[^\n]*$', re.MULTILINE);
	permalink_line = re.compile('^[^\n]*<h3>Permanent link to this comic: http://xkcd\.com/(\d+)/</h3>[^\n]*$', re.MULTILINE);
	transcript_line = re.compile('^[^\n]*<div id="transcript" style="display: none">(.*?)</div>[^\n]*$', re.MULTILINE | re.DOTALL);
	archive_line = re.compile('^[^\n]*<a href="/(\d+)/" title="(\d{4,4}-\d{1,2}-\d{1,2})">([^\n]*)</a><br/>[^\n]*$', re.MULTILINE);

	# read the cache from the file
	comics = read_cache()

	# if we were told to grab all the comics
	if not sigint:
		if args.cache_all:
			download_archive(comics)
			for num in sorted(comics.keys()):
				if sigint:
					break
				fetch(comics, num)

	if not sigint:
		comic_list = []
		if len(args.comic_nums) > 0:
			# if we were told which comics to grab
			comic_list.append(fetch(comics, args.comic_nums[0]))
			for num in args.comic_nums[1:]:
				if sigint:
					break
				comic_list.append(fetch(comics, num))
		else:
			# lacking specific instructions, fetch the latest comic
			if not args.cache_all:
				download_archive(comics)
			if not sigint:
				comic_list.append(fetch(comics, max(comics.keys())))
		if not sigint:
			output_lines = []
			for comic in comic_list:
				comic.write_comic(output_lines)
			for line in output_lines:
				sys.stdout.write(line + '\n')

	# write the cache to the file
	write_cache(comics)
