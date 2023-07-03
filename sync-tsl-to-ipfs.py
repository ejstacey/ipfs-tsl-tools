#!/bin/env python

import pprint
import requests
from pathlib import Path

pp = pprint.PrettyPrinter(indent=4)

###### Settings - do this with a config file in the future, maybe
settings = {
    # RPC port of the ipfs server. You may have to make it listen on your local network IP, or set up an SSH tunnel
    'ipfsServer'                : '192.168.1.55',
    # RPC port of the ipfs server
    'ipfsPort'                  : 15001,
    # the local directory TSL is mounted into on the machine running this script
    'tslDirectory'              : '/mnt/tsl',
    # the directory TSL is mounted into on the docker container or server running ipfs
    'remoteTslDirectory'        : '/data/mounted-files/tsl',
    # if verify is set to True, each file in TSL will be hashed and checked against what's currently in IPFS
    # if verify is set to False, it just works off filesize (and file name, which is the "key")
    'verify'                    : True
}

def grabCurrentIpfs(settings, directory="/"):
    ipfsDb = {}

    url = "http://" + settings['ipfsServer'] + ":" + settings['ipfsPort'] + "/api/v0/files/ls"
    args = {
        'arg'   : directory,
        'long'  : True
    }
    r = requests.post(url, params=args)
    entries = []
    if r.json()['Entries'] is not None:
        entries = r.json()['Entries']
    for entry in entries:
        # pp.pprint(entry)
        match entry['Type']:
            case 0:
                # file, grab its info.. but we want it to be in the proper structure of the db
                entry['Path'] = directory
                ipfsDb[entry['Name']] = entry
            case 1:
                # directory, go deeper
                newDirectory = directory + entry['Name'] + '/'
                tmpData = grabCurrentIpfs(settings, newDirectory)
                ipfsDb[entry['Name'] + '/'] = tmpData
            case _:
                pp.pprint(entry)
                raise Exception('Unknown IPFS type: ' + entry['Type'])

    return ipfsDb

def grabCurrentTsl(directory):
    tslDb = {}

    dir = Path(directory)
    for path in dir.iterdir():
        # ignore anything starting with a /. in the path (file or directory starting with .)
        if '/.' in str(path):
            continue

        if (path.is_file()):
            stats = path.stat()
            fileEntry = {
                'name' : path.name,
                'size' : stats.st_size
            }
            tslDb[path.name] = fileEntry
        elif (path.is_dir()):
            # directory, go deeper
            newDirectory = str(path)
            tempDir = str(path).split('/').pop() + '/'
            tslDb[tempDir] = grabCurrentTsl(newDirectory)
        else:
            raise Exception("Not recognised as a file or a directory: " + str(path))

    # pp.pprint(tslDb)
    return tslDb

def getIpfsHash(settings):
    url = "http://" + settings['ipfsServer'] + ":" + str(settings['ipfsPort']) + "/api/v0/filestore/verify"
    r = requests.post(url)
    print(r.json())    

def parsePaths(settings, path, ipfsDb, tslDb):    
    for path in ipfsDb:
        if path not in tslDb:
            # everything in this path needs to be removed from ipfs
            print("removals")
        else:
            # compare the entries.
            if path.endswith('/'):
                # we have a deeper path, check it
                parsePaths(settings, path, ipfsDb[path], tslDb[path])
            else:
                # we have a file, finally compare
                if settings['verify']:
                    hash = getIpfsHash(settings, ipfsDb[path]['Path'])
                    if ipfsDb[path]['Hash'] != hash:
                        print("No match, reupload.")
                else:
                    if ipfsDb[path]['size'] != tslDb[path]['size']:
                        print("hi")

    for path in tslDb:
        if path not in ipfsDb:
            # everything in this path needs to be added to ipfs
            print("additions")


# # Load/set up the existing ipfs info
# ipfsDb = {}
# settings['ipfsPort'] = str(settings['ipfsPort'])
# print("Loading IPFS info from " + settings['ipfsServer'] + ":" + settings['ipfsPort'] + ".")
# ipfsDb['The Silent Library/'] = grabCurrentIpfs(settings, "/The Silent Library/")
# print("Done loading IPFS info.")

# # Load/set up the current TSL info
# tslDb = {}
# print("Loading TSL Library from " + settings['tslDirectory'])
# tslDb['The Silent Library/'] = grabCurrentTsl(settings['tslDirectory'])
# print("Done loading TSL Library.")

# # OK we have two dicts full of all the info we care about
# # parse it.
# parsePaths(settings, '/The Silent Library/', ipfsDb, tslDb)
getIpfsHash(settings)