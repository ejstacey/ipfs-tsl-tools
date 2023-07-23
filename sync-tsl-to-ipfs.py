#!/bin/env python

import pprint
import json
import requests
from requests_toolbelt.utils import dump
# import asyncio
# import aioipfs
from requests.exceptions import HTTPError
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
    # A verify takes hours.
    'verify'                    : False,
    # if refresh is set to False, and json db files exist, it'll use existing json db files
    # if refresh is set to True, or the json db files don't exist, it'll generate the db files (and dump them)
    'refresh'                   : False,
    # The name of the file to use for the ipfsDb db save
    'ipfsDbFileName'            : 'ipfsDb.json',
    # The name of the file to use for the tslDb db save
    'tslDbFileName'             : 'tslDb.json'
}

def grabCurrentIpfs(settings, directory="/"):
    ipfsDb = {}

    # filesObj = settings['ipfsSession'].files.ls(path=directory,params={'long': True})

    url = "http://" + settings['ipfsServer'] + ":" + settings['ipfsPort'] + "/api/v0/files/ls"
    args = {
        'arg'   : directory,
        'long'  : True
    }
    r = requests.post(url, params=args)
    result = r.json()
    # pp.pprint(result)
    if "Entries" in result:
        if result["Entries"] is not None:
            entries = result['Entries']
            for entry in entries:
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

def grabCurrentTsl(settings, directory):
    tslDb = {}

    dir = Path(directory)
    for path in dir.iterdir():
        # ignore anything starting with a /. in the path (file or directory starting with .)
        if '/.' in str(path):
            continue

        if (path.is_file()):
            stats = path.stat()
            mfsPath = str(path).replace(settings['tslDirectory'], '/The Silent Library')
            fileEntry = {
                'name'          : path.name,
                'size'          : stats.st_size,
                'remotePath'    : str(path).replace(settings['tslDirectory'], settings['remoteTslDirectory']),
                'mfsPath'       : mfsPath,
                'localPath'     : str(path)
            }
            tslDb[path.name] = fileEntry
        elif (path.is_dir()):
            # directory, go deeper
            newDirectory = str(path)
            tempDir = str(path).split('/').pop() + '/'
            tslDb[tempDir] = grabCurrentTsl(settings, newDirectory)
        else:
            raise Exception("Not recognised as a file or a directory: " + str(path))

    # pp.pprint(tslDb)
    return tslDb

def verifyIpfsLibrary(settings):
    url = "http://" + settings['ipfsServer'] + ":" + str(settings['ipfsPort']) + "/api/v0/filestore/verify"
    r = requests.post(url)
    print(r.json())    

def parsePaths(settings, path, ipfsDb, tslDb, fullPath=""):
    fullPath += path
    for path in ipfsDb:
        if path not in tslDb:
            # everything in this path needs to be removed from ipfs
            removeEntries(settings, ipfsDb[path])
            # print("remove: " + fullPath + path)
        else:
            # compare the entries.
            if path.endswith('/'):
                # we have a deeper path, check it
                parsePaths(settings, path, ipfsDb[path], tslDb[path], fullPath)
            else:
                # we have a file, finally compare
                # if settings['verify']:
                #     hash = getIpfsHash(settings, ipfsDb[path]['Path'])
                #     if ipfsDb[path]['Hash'] != hash:
                #         print("No match, reupload.")
                # else:
                # pp.pprint(ipfsDb[path])
                # pp.pprint(tslDb[path])
                # pp.pprint(path)
                if ipfsDb[path]['Size'] != tslDb[path]['size']:
                    print("update: " +  fullPath + path)

    for path in tslDb:
        if path not in ipfsDb:
            # everything in this path needs to be added to ipfs
            # print("add: " + fullPath + path)
            if path.endswith('/'):
                # we have a deeper path, check it
                parsePaths(settings, path, {}, tslDb[path], fullPath)
            else:
                addEntries(settings, tslDb[path])

def removeEntries(settings, entry):
    url = "http://" + settings['ipfsServer'] + ":" + settings['ipfsPort'] + "/api/v0/files/rm"
    args = {
        'arg'           : entry['Path'] + entry['Name'],
        'recursive'     : True
    }
    print('Removing ' + entry['Path'] + entry['Name'])
    # pp.pprint(entry)
    r = requests.post(url, params=args)
    r.raise_for_status()
    if (r.text == '' or 'file does not exist' in r.text):
        return
    else:
        raise Exception("Could not properly parse the return from a removal attempt of " + entry['Path'] + entry['Name'] + ":\n" + r.text)

def addEntries(settings, entry):
    url = "http://" + settings['ipfsServer'] + ":" + settings['ipfsPort'] + "/api/v0/add"
    args = {
        'quieter'       : 'true',
        'nocopy'        : 'true',
        'to-files'      : entry['mfsPath']
    }

    file = open(entry['localPath'], 'rb')

    files = {
            'file'          : (
                                entry['name'],
                                file,
                                'application/octet-stream',
                                {
                                    'Abspath': entry['remotePath']
                                }
                            )
            }
    
    print('Adding ' + entry['mfsPath'])
    try:
        # print(url)
        r = requests.post(url, params=args, files=files)

        # data = dump.dump_all (r)
        # print (data.decode ('utf-8'))

        # If the response was successful, no Exception will be raised
        r.raise_for_status()
    except HTTPError as http_err:
        if (r.status_code == 500):
            err = r.json()
            http_err = err['Message']
        raise Exception(f'HTTP error occurred: {http_err}')
    except Exception as err:
        raise Exception(f'Other error occurred: {err}')
    else:
        result = r.json()
        if ('Name' in result):
            return
        else:
            raise Exception("Could not properly parse the return from an addition attempt of " + entry['mfsPath'] + ".\n" + r.content())
        
def main():
    # Create IPFS session
    # headers = {"CustomHeader": "foobar"}
    # >>> client = ipfshttpclient.connect('/dns/ipfs-api.example.com/tcp/443/https', headers=headers)
    settings['ipfsPort'] = str(settings['ipfsPort'])
    settings['maddr'] = '/ip4/' + settings['ipfsServer'] + '/tcp/' + settings['ipfsPort']

    # Load/set up the existing ipfs info
    ipfsDb = {}
    dbFile = Path(settings['ipfsDbFileName'])
    if settings['refresh'] or not dbFile.is_file():
        print("Loading IPFS info from " + settings['ipfsServer'] + ":" + settings['ipfsPort'] + ".")
        ipfsDb['The Silent Library/'] = grabCurrentIpfs(settings, "/The Silent Library/")
        with open(settings['ipfsDbFileName'],"w") as file:
            file.write(json.dumps(ipfsDb))
    else:
        print("Loading IPFS info from existing file " + settings['ipfsDbFileName'] + ".")
        with open(settings['ipfsDbFileName'],"r") as file:
            ipfsDb = json.load(file)
    print("Done loading IPFS info.")

    # Load/set up the current TSL info
    tslDb = {}
    dbFile = Path(settings['tslDbFileName'])
    if settings['refresh'] or not dbFile.is_file():
        print("Loading TSL Library from " + settings['tslDirectory'])
        tslDb['The Silent Library/'] = grabCurrentTsl(settings, settings['tslDirectory'])
        with open(settings['tslDbFileName'],"w") as file:
            file.write(json.dumps(tslDb))
    else:
        print("Loading TSL Library from existing file " + settings['tslDbFileName'] + ".")
        with open(settings['tslDbFileName'],"r") as file:
            tslDb = json.load(file)
    print("Done loading TSL Library.")

    # entry = {
    #     'path'      : '/home/ejstacey/Hello.txt',
    #     'mfsPath'   : '/Hello.txt'
    # }
    # addEntries(settings=settings, entry=entry)
    # addDirectory(settings=settings, entry=entry)

    # OK we have two dicts full of all the info we care about
    # parse it.
    # print("ipfsDb:")
    # pp.pprint(ipfsDb)
    # print("tslDb:")
    # pp.pprint(tslDb)
    # print("parsing:")
    parsePaths(settings, '', ipfsDb, tslDb)
    # verifyIpfsLibrary(settings)

main()

