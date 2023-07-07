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
	shell "github.com/ipfs/go-ipfs-api"
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
	IpfsSession          *shell.Shell
}

func grabCurrentIpfs(settings Settings, path string) ipfsDir {
	var ipfsDir ipfsDir
	ipfsDir.FsPath = path
	lastDir := regexp.MustCompile(`^.+/([^/]+)$`)
	ipfsDir.Name = lastDir.ReplaceAllString(path, "$1")
	// spew.Dump(path)

	var sh = settings.IpfsSession

	ctx := context.Background()
	ipfsFiles, err := sh.FilesLs(ctx, path, shell.FilesLs.Stat(true))
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
			tslDir.Name = file.Name()
			tslDir.FsPath = fsPath
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

func main() {
	fmt.Println("Loading settings.")
	var settings = loadSettings()
	fmt.Println("Settings Loaded.")

	sh := shell.NewShell(settings.IpfsServer + ":" + settings.IpfsPort)
	settings.IpfsSession = sh

	var ipfsDb = loadIpfsDb(settings)
	var tslDb = loadTslDb(settings)

	spew.Dump(ipfsDb)
	spew.Dump(tslDb)
}
