from collections import defaultdict
from json import loads
from urllib import urlopen
from xml.dom.minidom import parse
API_KEY = ''
SCHEMAS = {}

def safe_print(s):
	try:
		print s.encode('utf-8'),
	except:
		pass
	print

def get_backpack(steamid64, name = ''):
	# No error checking - the calling function should account for bad API keys
	if name:
		safe_print( "Loading %s's backpack..." % name )
	quantities = defaultdict(int)
	for item in loads(
		urlopen( "http://api.steampowered.com/IEconItems_440/GetPlayerItems/v0001/?key=" +
			API_KEY + "&SteamID=%d" % steamid64 ).read()
	)["result"]["items"]:
		# This assumes there can't be multiple untradable items of the same type
		quantities[item["defindex"]] += 1
	return quantities

def query_schema(language = 'en'):
	global SCHEMAS
	if not language in SCHEMAS:
		SCHEMAS[language] = load_schema(language)
	return SCHEMAS[language]

def load_schema(language = 'en'):
	print 'Loading schema "%s"...' % language
	return {
		item["defindex"]:item for item in loads(
		urlopen( "http://api.steampowered.com/IEconItems_440/GetSchema/v0001/?key=" +
			API_KEY + "&language=" + language ).read()
		)["result"]["items"]
	}

def print_trade(friend_name, trade_to, trade_from, language = 'en', mutual_only = False):
	if mutual_only and not trade_to or not trade_from:
		return
	if not trade_to and not trade_from:
		return
	safe_print("\nPotential trades with %s:" % friend_name )
	for items, direction in zip((trade_to, trade_from), ("To:", "From:")):
		if items:
			print direction
			for item in items:
				safe_print( '\t' + query_schema(language)[item]["item_name"] )
			print

def check_pair(player_backpack, friend_backpack, filters, language):
	return tuple(
		[
			i for i, q in backpack1.iteritems() if
				q > 1 and backpack2[i] == 0 and
				query_schema(language)[i]["item_class"] not in filters
		] for backpack1, backpack2 in (
			(player_backpack, friend_backpack), (friend_backpack, player_backpack)
		)
	)

def get_friends_from_xml(xmldoc):
	return [
		int(friend.firstChild.nodeValue) for friend in xmldoc.getElementsByTagName('friend')
	]

def get_steamid64_from_xml(xmldoc):
	try:
		steamid64 = int( xmldoc.getElementsByTagName('steamID64')[0].firstChild.data )
	except IndexError:
		print "The specified profile %s could not be found." % friend_url
		return 0
	else:
		return steamid64

def get_potential_trades(
	player_steamid64, friend_steamid64s = [], filters = [], language = 'en',
	player_name = '', friend_names = defaultdict(str)
):
	if not friend_steamid64s:
		# The function will load the friend list if it wasn't provided
		friend_steamid64s = get_friends_from_xml(
			parse(
				urlopen( "http://steamcommunity.com/profiles/%s/friends?xml=1" % player_steamid64 )
			)
		)
	player_backpack = get_backpack( player_steamid64, player_name )
	for friend_steamid64 in friend_steamid64s:
		try:
			yield (
				friend_steamid64, check_pair(
					player_backpack,
					get_backpack(friend_steamid64, friend_names[friend_steamid64]),
					filters,
					language
				)
			)
		except KeyError:
			# This should only happen when the backpack is private
			if friend_names:
				safe_print( "Unable to load %s's backpack!" % friend_names[friend_steamid64] )
			# Tuple of two empty lists - neither of you have anything to give each other
			yield (friend_steamid64, ([],[]))

def get_player_summaries(steamid64s, online_only = False):
	# No error checking - the calling function should account for bad API keys
	summaries = loads(
		urlopen(
			'http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key=%s&steamids=%s' % (
				API_KEY, ','.join([str(id) for id in steamid64s])
			)
		).read()
	)["response"]["players"]
	if online_only:
		return [ player for player in summaries if player["personastate"] > 0 ]
	else:
		return summaries

if __name__ == "__main__":
	from argparse import ArgumentParser
	parser = ArgumentParser(description = "finds your duplicate items that your friend doesn't have and vice versa for each of your Steam friends")
	parser.add_argument('key', help='your API key')
	parser.add_argument('profile_url', help='the URL of your Steam profile')
	parser.add_argument('--online-only', action='store_true', help='skip offline friends')
	parser.add_argument('--mutual-only', action='store_true', help='only display potential trades when you both have something to give each other')
	parser.add_argument('--ignore-class', metavar='item_class', nargs='+', default=[], help='ignore items of the specified item class (such as "craft_item" or "tf_wearable")')
	parser.add_argument('--language', default='en', help='the ISO639-1 language code for the language all localized strings should be returned in.')
	parser.add_argument('--no-schema-cache', action='store_true', help='reload all schemas')
	parser.add_argument('--profile-urls', metavar='URL', nargs='+', default=[], help="Override player's friend list and use the specified profiles")
	args = parser.parse_args()
	
	from pickle import load, dump
	if not args.no_schema_cache:
		try:
			with open('tf2-schema-cache') as f:
				SCHEMAS = load(f)
		except:
			pass

	from sys import exit
	API_KEY = args.key
	profile_url = args.profile_url
	print 'Resolving "%s"...' % profile_url
	try:
		xmldoc = parse( urlopen( profile_url + "/friends?xml=1" ) )
	except IOError:
		exit("Invalid URL specified.")
	player_steamid64 = get_steamid64_from_xml(xmldoc)
	if not player_steamid64:
		exit("The specified profile could not be found.")
	player_name = xmldoc.getElementsByTagName('steamID')[0].firstChild.data
	if args.profile_urls:
		friend_steamids = []
		for url in args.profile_urls:
			print 'Resolving "%s"...' % url
			try:
				xmldoc = parse( urlopen( url + "/friends?xml=1" ) )
			except IOError:
				print "%s is an invalid URL." % url
			friend_steamid64 = get_steamid64_from_xml(xmldoc)
			if friend_steamid64:
				friend_steamids.append(friend_steamid64)
	else:
		friend_steamids = get_friends_from_xml(xmldoc)
	if len(friend_steamids) < 1:
		exit("No friends found")
	try:
		friend_summaries = get_player_summaries(
			friend_steamids,
			args.online_only
		)
	except IOError as (errstr, errcode, errmsg, headers):
		if errcode == 401:
			exit("Invalid API key.")
		else:
			raise
	
	friend_names = { friend["steamid"]:friend["personaname"] for friend in friend_summaries }
	for friend_steamid64, (trade_to, trade_from) in get_potential_trades(
		player_steamid64,
		[ friend["steamid"] for friend in friend_summaries ],
		args.ignore_class,
		args.language,
		player_name,
		friend_names
	):
		print_trade(
			friend_names[friend_steamid64], trade_to, trade_from, args.language, args.mutual_only
		)
	
	f = open('tf2-schema-cache', 'w')
	dump(SCHEMAS, f)
	f.close()