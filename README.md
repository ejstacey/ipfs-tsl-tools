Script for keeping a disk-based library in sync with what IPFS provides.

This scans a local library and the IPFS MFS library, then adds/removes files from the IPFS MFS library as needed.

This requires a config file, done in the ini style format. An example file is included. You can use full network paths in Windows with it.

An example for The Silent Library is:

```ini
[options]
# if refresh is set to False, and json db files exist, it'll use existing json db files
# if refresh is set to True, or the json db files don't exist, it'll generate the db files (and dump them)
refresh = True
# The name of the file to use for the ipfsDb db save
ipfsDbFileName = ipfsDb-tsl.json
# The name of the file to use for the tslDb db save
tslDbFileName = tslDb-tsl.json

[remote]
# RPC port of the ipfs server. You may have to make it listen on your local network IP, or set up an SSH tunnel
ipfsServer = localhost
# RPC port of the ipfs server
ipfsPort = 5001
# the directory TSL is mounted into on the docker container or server running ipfs
tslDirectory = \\192.168.2.55\data\ipfs\tsl
# the directory that this collection lives under in the Mutable File System (MFS)
mfsRootDirectory = The Silent Library
# the name of the key to use for publishing the entire thing to IPNS (it's a name you make up)
ipnsKeyName = tsl

[local]
# the local directory TSL is mounted into on the machine running this script
tslDirectory = \\192.168.2.55\data\Videos\The Silent Library
```

An example for The Silent Library Raw Wing is:
```ini
[options]
# if refresh is set to False, and json db files exist, it'll use existing json db files
# if refresh is set to True, or the json db files don't exist, it'll generate the db files (and dump them)
refresh = True
# The name of the file to use for the ipfsDb db save
ipfsDbFileName = ipfsDb-tsl-raws.json
# The name of the file to use for the tslDb db save
tslDbFileName = tslDb-tsl-raws.json

[remote]
# RPC port of the ipfs server. You may have to make it listen on your local network IP, or set up an SSH tunnel
ipfsServer = localhost
# RPC port of the ipfs server
ipfsPort = 5001
# the directory TSL is mounted into on the docker container or server running ipfs
tslDirectory = \\192.168.2.55\data\ipfs\tsl-raws
# the directory that this collection lives under in the Mutable File System (MFS)
mfsRootDirectory = The Silent Library Raw Wing
# the name of the key to use for publishing the entire thing to IPNS (it's a name you make up)
ipnsKeyName = tsl-raws

[local]
# the local directory TSL is mounted into on the machine running this script
tslDirectory = \\192.168.2.55\data\Videos\The Silent Library Raw Wing
```

You can of course adjust things to your liking. You should leave `refresh` to True though. It's false only for debugging.

Execute the script with `python sync-tsl-to-ipfs.py --config tsl.cfg`

If you omit the --config argument it will look for a file called 'settings.cfg'.

Old scripts can be found in [https://github.com/ejstacey/ipfs-tsl-tools/tree/1f109d22344c50a1d9e8d0335895daacc259f7fd](this commit).
The broken go version (no uploading support, just scanning and comparing) is [https://github.com/ejstacey/ipfs-tsl-tools/tree/8bcb5f8423f3baa284aaed96f83fbf39c912c976/sync-tsl-to-ipfs-go](this commit).