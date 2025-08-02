#!/bin/bash
list="$1"

curl https://iptoasn.com/data/ip2asn-v4.tsv.gz | gzip -d >/tmp/asndb.tsv

rm /tmp/asn-processed.txt
cat "./input/$list/ASN.txt" | grep -v '^#' | awk '{print $1}' | grep '^AS' | while read asn; do
    echo "Processing $asn"
    awk '{if($3 == '${asn:2}') print "ipcalc -rn "$1"-"$2" | tail -n+2"}' /tmp/asndb.tsv | bash >>/tmp/asn-processed.txt
done
