#!/bin/sh

parseDir() {
	for dir in "$*"/*;
	do
		dir=`echo "$dir" | sed -e "s/ /\\ /g"`
		tslDir=`echo "$dir" | sed -e "s/\/data\/mounted-files\/tsl\///g" | sed -e "s/ /\\ /g"`
		tslDir=`dirname "$tslDir"`
		tslFile=`basename "$dir"`
		`ipfs files mkdir -p "/The Silent Library/$tslDir"`

		if [ "${tslFire:0:1}" == "." ];
		then
			continue;
		fi;
	
		if [ -d "$dir" ];
		then
			parseDir "$dir";
		fi
		if [ -f "$dir" ];
		then
			hash=`ipfs add --quieter --recursive --nocopy --to-files "/The Silent Library/$tslDir/$tslFile" "$dir"`
			echo "${tslDir}:${tslFile}:$hash" >> hash-list;
		fi
	done
}

parseDir "/data/mounted-files/tsl";
