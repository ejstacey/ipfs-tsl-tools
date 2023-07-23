package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"regexp"
	"strings"

	"github.com/adhocore/jsonc"
	"github.com/davecgh/go-spew/spew"
	pathMod "github.com/ipfs/boxo/path"
	"github.com/ipfs/kubo/client/rpc"
	ma "github.com/multiformats/go-multiaddr"
)

type ipfsFile struct {
	Name string `json:"ipfsfilename"`
	Type uint8  `json:"ipfsfiletype"`
	Size uint64 `json:"ipfsfilesize"`
	Hash string `json:"ipfsfilehash"`
	Path string `json:"ipfsfilepath"`
}

type ipfsDir struct {
	Name   string     `json:"ipfsdirname"`
	FsPath string     `json:"ipfsdirfspath"`
	Dirs   []ipfsDir  `json:"ipfsdirdirs"`
	Files  []ipfsFile `json:"ipfsdirfiles"`
}

type tslFile struct {
	Name    string `json:"tsldirname"`
	Size    int64  `json:"tsldirsize"`
	Path    string `json:"tsldirpath"`
	MfsPath string `json:"tsldirmfspath"`
}

type tslDir struct {
	Name   string    `json:"tsldirfilename"`
	FsPath string    `json:"tsldirfspath"`
	Dirs   []tslDir  `json:"tsldirdirs"`
	Files  []tslFile `json:"tsldirfiles"`
}

type Settings struct {
	IpfsServer           string `json:"IpfsServer"`
	IpfsPort             string `json:"IpfsPort"`
	IpfsMfsRootDirectory string `json:"IpfsMfsRootDirectory"`
	TslDirectory         string `json:"TslDirectory"`
	RemoteTslDirectory   string `json:"RemoteTslDirectory"`
	Verify               bool   `json:"Verify"`
	Refresh              bool   `json:"Refresh"`
	IpfsDbFileName       string `json:"IpfsDbFileName"`
	TslDbFileName        string `json:"TslDbFileName"`
	IpfsSession          *rpc.HttpApi
	MAddr                string
}

type dbOpts struct {
	settings Settings
	path     string
	ipfsDb   ipfsDir
	tslDb    tslDir
	fullPath string
}

func grabCurrentIpfs(settings Settings, path string) ipfsDir {
	var ipfsDir ipfsDir
	ipfsDir.FsPath = path
	lastDir := regexp.MustCompile(`^.+/([^/]+)$`)
	ipfsDir.Name = lastDir.ReplaceAllString(path, "$1")
	// spew.Dump(path)

	var sh = settings.IpfsSession
	var unixFs = sh.Unixfs()

	ctx := context.Background()
	var pathObj = pathMod.Path(path)
	ipfsFiles, err := unixFs.Ls(ctx, pathObj, shell.FilesLs.Stat(true))
	if err != nil {
		if !strings.Contains(err.Error(), "no such file or directory") {
			fmt.Fprintf(os.Stderr, "error: %s", err)
		}
	} else {
		for i := 0; i < len(ipfsFiles); i++ {
			var entry = ipfsFiles[i]
			// spew.Dump(entry)
			ipfsDir.Name = lastDir.ReplaceAllString(path, "$1")
			if entry.Type == 1 {
				// a directory. go deeper.
				var contents = grabCurrentIpfs(settings, path+"/"+entry.Name)
				// spew.Dump(contents)

				ipfsDir.Dirs = append(ipfsDir.Dirs, contents)
			} else if entry.Type == 0 {
				// a file, capture it
				var file ipfsFile

				file.Hash = entry.Hash
				file.Name = entry.Name
				file.Size = entry.Size
				file.Type = entry.Type
				file.Path = path + "/" + entry.Name

				ipfsDir.Files = append(ipfsDir.Files, file)
			}
		}
	}

	return ipfsDir
}

func grabCurrentTsl(settings Settings, tslFsDir string) tslDir {
	var tslDir tslDir

	files, err := os.ReadDir(tslFsDir)
	if err != nil {
		log.Fatal(err)
	}

	if len(files) > 0 {
		for _, file := range files {
			dotDir := regexp.MustCompile(`^\.`)
			if dotDir.MatchString(file.Name()) {
				continue
			}

			var fsPath = tslFsDir + "/" + file.Name()
			lastDir := regexp.MustCompile(`^.+/([^/]+)$`)
			tslDir.Name = lastDir.ReplaceAllString(tslFsDir, "$1")
			tslDir.FsPath = tslFsDir

			if file.Type().IsDir() {
				// directory, go deeper
				var contents = grabCurrentTsl(settings, fsPath)
				tslDir.Dirs = append(tslDir.Dirs, contents)
			} else if file.Type().IsRegular() {
				// a file, what we expect.
				var tslFile tslFile
				tslFile.Name = file.Name()
				var fileInfo, err = file.Info()
				if err != nil {
					log.Fatal(err)
				}
				tslFile.Size = fileInfo.Size()

				var fullPath = fsPath
				fullPath = strings.ReplaceAll(fullPath, settings.TslDirectory, settings.RemoteTslDirectory)
				tslFile.Path = fullPath

				var mfsPath = fsPath
				mfsPath = strings.ReplaceAll(mfsPath, settings.TslDirectory, settings.IpfsMfsRootDirectory)
				tslFile.MfsPath = mfsPath

				tslDir.Files = append(tslDir.Files, tslFile)
			}
		}
	} else {
		lastDir := regexp.MustCompile(`^.+/([^/]+)$`)
		tslDir.Name = lastDir.ReplaceAllString(tslFsDir, "$1")
		tslDir.FsPath = tslFsDir
	}
	return tslDir
}

func loadSettings() Settings {
	j := jsonc.New()
	input, err := os.ReadFile("settings.json")
	if err != nil {
		log.Fatal(err)
	}

	input = j.Strip(input)
	var settings Settings
	err = json.Unmarshal(input, &settings)
	if err != nil {
		log.Fatal(err)
	}

	if len(settings.IpfsMfsRootDirectory) > 1 {
		var s = settings.IpfsMfsRootDirectory
		last := s[len(s)-1:]
		if last == "/" {
			newName := s[0 : len(s)-1]
			settings.IpfsMfsRootDirectory = newName
		}

	}

	settings.MAddr = "/ip4/" + settings.IpfsServer + "/tcp/" + settings.IpfsPort

	return settings
}

func loadIpfsDb(settings Settings) ipfsDir {
	var refresh = false
	var ipfsDb ipfsDir

	input, err := os.ReadFile(settings.IpfsDbFileName)
	if err != nil {
		if !settings.Refresh {
			fmt.Println("Could not open " + settings.IpfsDbFileName + ". Doing full refresh. Error: " + err.Error())
		}
		refresh = true
	} else {
		if !settings.Refresh {
			fmt.Println("Loading ipfsDb from " + settings.IpfsDbFileName)
			err = json.Unmarshal(input, &ipfsDb)
			if err != nil {
				log.Fatal("Trying to read " + settings.IpfsDbFileName + ": " + err.Error())
			}
			fmt.Println("Done.")
		} else {
			refresh = true
		}
	}

	if refresh {
		fmt.Println("Loading ipfsDb from " + settings.IpfsServer + ":" + settings.IpfsPort)
		ipfsDb = grabCurrentIpfs(settings, settings.IpfsMfsRootDirectory)
		file, err := json.Marshal(ipfsDb)
		if err != nil {
			log.Fatal("Trying to write DB file " + settings.IpfsDbFileName + ": " + err.Error())
		}

		err = os.WriteFile(settings.IpfsDbFileName, file, 0644)
		if err != nil {
			log.Fatal("Trying to write DB file " + settings.IpfsDbFileName + ": " + err.Error())
		}

		fmt.Println("Done.")
	}

	return ipfsDb
}

func loadTslDb(settings Settings) tslDir {
	var refresh = false
	var tslDb tslDir

	input, err := os.ReadFile(settings.TslDbFileName)
	if err != nil {
		if !settings.Refresh {
			fmt.Println("Could not open " + settings.TslDbFileName + ". Doing full refresh. Error: " + err.Error())
		}
		refresh = true
	} else {
		if !settings.Refresh {
			fmt.Println("Loading tslDb from " + settings.TslDbFileName)
			err = json.Unmarshal(input, &tslDb)
			if err != nil {
				log.Fatal("Trying to read " + settings.TslDbFileName + ": " + err.Error())
			}
			fmt.Println("Done.")
		} else {
			refresh = true
		}
	}

	if refresh {
		fmt.Println("Loading tslDb from " + settings.TslDirectory)
		tslDb = grabCurrentTsl(settings, settings.TslDirectory)
		file, err := json.Marshal(tslDb)
		if err != nil {
			log.Fatal("Trying to write DB file " + settings.TslDbFileName + ": " + err.Error())
		}

		err = os.WriteFile(settings.TslDbFileName, file, 0644)
		if err != nil {
			log.Fatal("Trying to write DB file " + settings.TslDbFileName + ": " + err.Error())
		}

		fmt.Println("Done.")
	}

	return tslDb
}

func compareDbs(opts dbOpts) {
	if opts.fullPath != "" {
		opts.fullPath += "/" + opts.path
	} else {
		opts.fullPath += opts.path
	}
	spew.Dump(opts.fullPath)
	for _, ipfsFile := range opts.ipfsDb.Files {
		var found = false
		var update = false

		// handle the files here
		for _, tslFile := range opts.tslDb.Files {
			// fmt.Println("Comparing files (ipfs source): " + ipfsFile.Name + " to " + tslFile.Name)
			if tslFile.Name == ipfsFile.Name {
				found = true
				if tslFile.Size != int64(ipfsFile.Size) {
					update = true
					fmt.Println("updating: " + ipfsFile.Name)
				}
				break
			}
		}
		if !found {
			fmt.Println("removing: " + ipfsFile.Name)
		} else {
			if !update {
				// fmt.Println("Match")
			}
		}
	}

	for _, tslFile := range opts.tslDb.Files {
		var found = false

		// handle the files here
		for _, ipfsFile := range opts.ipfsDb.Files {
			// fmt.Println("Comparing files (tsl source): " + ipfsFile.Name + " to " + tslFile.Name)
			if ipfsFile.Name == tslFile.Name {
				// fmt.Println("Match")
				found = true
				break
			}
		}
		if !found {
			fmt.Println("adding: " + tslFile.Name)
		}
	}

	// handle the subdirectories here
	for _, ipfsDir := range opts.ipfsDb.Dirs {
		var found = false
		var savedTslDir tslDir

		for _, tslDir := range opts.tslDb.Dirs {
			// fmt.Println("Comparing dirs (ipfs source): " + ipfsDir.Name + " to " + tslDir.Name)

			if tslDir.Name == ipfsDir.Name {
				found = true
				// fmt.Println("Match")
				savedTslDir = tslDir
				break
			}
		}

		if found {
			var newOpts dbOpts
			newOpts.settings = opts.settings
			newOpts.path = ipfsDir.Name
			newOpts.ipfsDb = ipfsDir
			newOpts.tslDb = savedTslDir
			newOpts.fullPath = opts.fullPath
			compareDbs(newOpts)
		} else {

			fmt.Println("removing dir: " + ipfsDir.Name)
		}
	}
	for _, tslDir := range opts.tslDb.Dirs {
		var found = false

		for _, ipfsDir := range opts.ipfsDb.Dirs {
			// fmt.Println("Comparing dirs (tsl source): " + tslDir.Name + " to " + ipfsDir.Name)

			if tslDir.Name == ipfsDir.Name {
				// fmt.Println("Match")
				found = true
				break
			}
		}

		if !found {
			fmt.Println("adding dir: " + tslDir.Name)
		}
	}
}

// def parsePaths(settings, path, ipfsDb, tslDb, fullPath=""):
//     fullPath += path
//     for path in ipfsDb:
//         if path not in tslDb:
//             # everything in this path needs to be removed from ipfs
//             removeEntries(settings, ipfsDb[path])
//             # print("remove: " + fullPath + path)
//         else:
//             # compare the entries.
//             if path.endswith('/'):
//                 # we have a deeper path, check it
//                 parsePaths(settings, path, ipfsDb[path], tslDb[path], fullPath)
//             else:
//                 # we have a file, finally compare
//                 # if settings['verify']:
//                 #     hash = getIpfsHash(settings, ipfsDb[path]['Path'])
//                 #     if ipfsDb[path]['Hash'] != hash:
//                 #         print("No match, reupload.")
//                 # else:
//                 # pp.pprint(ipfsDb[path])
//                 # pp.pprint(tslDb[path])
//                 # pp.pprint(path)
//                 if ipfsDb[path]['Size'] != tslDb[path]['size']:
//                     print("update: " +  fullPath + path)

//     for path in tslDb:
//         if path not in ipfsDb:
//             # everything in this path needs to be added to ipfs
//             # print("add: " + fullPath + path)
//             if path.endswith('/'):
//                 # we have a deeper path, check it
//                 parsePaths(settings, path, {}, tslDb[path], fullPath)
//             else:
//                 addEntries(settings, tslDb[path])

func main() {
	fmt.Println("Loading settings.")
	var settings = loadSettings()
	fmt.Println("Settings Loaded.")

	m1, err := ma.NewMultiaddr("/ip4/127.0.0.1/udp/1234")
	if err != nil {
		log.Fatal("Trying to create multiaddr entry with " + settings.IpfsServer + ":" + settings.IpfsPort + ": " + err.Error())
	}
	sh, err := rpc.NewApi(m1)
	if err != nil {
		fmt.Printf(err.Error())
		return
	}

	// sh := shell.NewShell(settings.IpfsServer + ":" + settings.IpfsPort)
	settings.IpfsSession = sh

	var ipfsDb = loadIpfsDb(settings)
	var tslDb = loadTslDb(settings)

	var opts dbOpts
	opts.settings = settings
	opts.path = settings.IpfsMfsRootDirectory
	opts.ipfsDb = ipfsDb
	opts.tslDb = tslDb
	opts.fullPath = ""
	compareDbs(opts)
	// spew.Dump(ipfsDb)
	// spew.Dump(tslDb)
}
