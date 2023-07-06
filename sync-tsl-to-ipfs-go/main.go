package main

import (
	"context"
	"fmt"
	"os"

	"github.com/davecgh/go-spew/spew"
	shell "github.com/ipfs/go-ipfs-api"
)

type ipfsFile struct {
	Name string
	Type uint8
	Size uint64
	Hash string
	Path string
}

type ipfsDir struct {
	Name   string
	fsPath string
	Dirs   []ipfsDir
	Files  []ipfsFile
}

type tslFile struct {
	Name    string
	Size    int
	Path    string
	mfsPath string
}

type tslDir struct {
	Name   string
	fsPath string
	Dirs   []tslDir
	Files  []tslFile
}

func grabCurrentIpfs(path string, sh *shell.Shell) ipfsDir {
	var ipfsDir ipfsDir

	ctx := context.Background()
	ipfsFiles, err := sh.FilesLs(ctx, path, shell.FilesLs.Stat(true))
	if err != nil {
		fmt.Fprintf(os.Stderr, "error: %s", err)
		os.Exit(1)
	}
	for i := 0; i < len(ipfsFiles); i++ {
		var entry = ipfsFiles[i]
		if entry.Type == 1 {
			// a directory. go deeper.
			var contents = grabCurrentIpfs(path, sh)
		} else if entry.Type == 2 {
			// a file, capture it
			var file ipfsFile

			file.Hash = entry.Hash
			file.Name = entry.Name
			file.Size = entry.Size
			file.Type = entry.Type
			file.Path = path

			ipfsDir.Files = append(ipfsDir.Files, file)
		}
	}

	return ipfsDir
}

func main() {
	spew.Dump("beginning")

	sh := shell.NewShell("192.168.1.55:15001")
	var ipfsDb ipfsDir

	ipfsDb = grabCurrentIpfs("/The Silent Library", sh)
}
