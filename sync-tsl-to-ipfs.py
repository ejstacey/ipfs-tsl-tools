#!/bin/env python3

import pprint
import json
import requests
from requests_toolbelt.utils import dump
import argparse
import configparser
from requests.exceptions import HTTPError
from pathlib import Path

pp = pprint.PrettyPrinter(indent=4)

###### See if a different config file is specified
parser = argparse.ArgumentParser(
    prog='sync-tsl-to-ipfs',
    description='This program tries to make sure the local directory matches what the IPFS thinks is correct. It adds/removes files to the IPFS directory as necessary.'
)

parser.add_argument('--config', '-c',
                    action='store',
                    default='settings.cfg',
                    help='configuration filename (default: settings.cfg)'
)
args = parser.parse_args()

###### Settings load
config = configparser.RawConfigParser()
config.read(args.config)

settings = {}
settings['remote'] = dict(config.items('remote'))
settings['options'] = dict(config.items('options'))
settings['local'] = dict(config.items('local'))

def grabCurrentIpfs(settings, directory="/"):
    ipfsDb = {}

    # filesObj = settings['ipfsSession'].files.ls(path=directory,params={'long': True})

    url = "http://" + settings['remote']['ipfsserver'] + ":" + settings['remote']['ipfsport'] + "/api/v0/files/ls"
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
                if entry['Type'] == 0:
                    # file, grab its info.. but we want it to be in the proper structure of the db
                    entry['Path'] = directory
                    ipfsDb[entry['Name']] = entry
                elif entry['Type'] == 1:
                    # directory, go deeper
                    newDirectory = directory + entry['Name'] + '/'
                    tmpData = grabCurrentIpfs(settings, newDirectory)
                    ipfsDb[entry['Name'] + '/'] = tmpData
                else:
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
            mfsPath = str(path).replace(settings['local']['tsldirectory'], '/The Silent Library')
            fileEntry = {
                'name'          : path.name,
                'size'          : stats.st_size,
                'remotePath'    : str(path).replace(settings['local']['tsldirectory'], settings['remote']['tsldirectory']),
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
    url = "http://" + settings['remote']['ipfsserver'] + ":" + str(settings['remote']['ipfsport']) + "/api/v0/filestore/verify"
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
    url = "http://" + settings['remote']['ipfsserver'] + ":" + settings['remote']['ipfsport'] + "/api/v0/files/rm"
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
    url = "http://" + settings['remote']['ipfsserver'] + ":" + settings['remote']['ipfsport'] + "/api/v0/add"
    args = {
        'quieter'       : 'true',
        'nocopy'        : 'true',
        'to-files'      : entry['mfsPath']
    }

    # file = open(entry['localPath'], 'rb')


    # files = {
    #         'file'          : (
    #                             entry['name'],
    #                             file,
    #                             'application/octet-stream',
    #                             {
    #                                 'Abspath': entry['remotePath']
    #                             }
    #                         )
    #         }

    headers = {
        'Abspath': entry['remotePath']
    }
    
    print('Adding ' + entry['mfsPath'])
    try:
        # print(url)
        with open(entry['localPath'], 'rb') as file:
            r = requests.post(url, data=file, headers=headers)
        # r = requests.post(url, params=args, files=files)

        data = dump.dump_all (r)
        print (data.decode ('utf-8'))

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
    settings['remote']['ipfsport'] = str(settings['remote']['ipfsport'])
    settings['remote']['maddr'] = '/ip4/' + settings['remote']['ipfsserver'] + '/tcp/' + settings['remote']['ipfsport']

    # Load/set up the existing ipfs info
    ipfsDb = {}
    dbFile = Path(settings['options']['ipfsdbfilename'])
    if settings['options']['refresh'] or not dbFile.is_file():
        print("Loading IPFS info from " + settings['remote']['ipfsserver'] + ":" + settings['remote']['ipfsport'] + ".")
        ipfsDb['The Silent Library/'] = grabCurrentIpfs(settings, "/The Silent Library/")
        with open(settings['options']['ipfsdbfilename'],"w") as file:
            file.write(json.dumps(ipfsDb))
    else:
        print("Loading IPFS info from existing file " + settings['options']['ipfsdbfilename'] + ".")
        with open(settings['options']['ipfsdbfilename'],"r") as file:
            ipfsDb = json.load(file)
    print("Done loading IPFS info.")

    # Load/set up the current TSL info
    tslDb = {}
    dbFile = Path(settings['options']['tsldbfilename'])
    if settings['options']['refresh'] or not dbFile.is_file():
        print("Loading TSL Library from " + settings['local']['tsldirectory'])
        tslDb['The Silent Library/'] = grabCurrentTsl(settings, settings['local']['tsldirectory'])
        with open(settings['options']['tsldbfilename'],"w") as file:
            file.write(json.dumps(tslDb))
    else:
        print("Loading TSL Library from existing file " + settings['options']['tsldbfilename'] + ".")
        with open(settings['options']['tsldbfilename'],"r") as file:
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

