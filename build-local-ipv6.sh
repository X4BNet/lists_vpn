#!/bin/bash
list="$1"

curl https://iptoasn.com/data/ip2asn-v6.tsv.gz | gzip -d >/tmp/asndb-ipv6.tsv

rm /tmp/asn-processed-ipv6.txt
cat "./input/$list/ASN.txt" | grep -v '^#' | awk '{print $1}' | grep '^AS' | while read -r asn; do
    echo "Processing $asn"
    awk -v asn="${asn:2}" '$3 == asn {print $1"-"$2}' /tmp/asndb-ipv6.tsv | while read -r range; do
        start=$(echo "$range" | cut -d'-' -f1)
        end=$(echo "$range" | cut -d'-' -f2)
        python3 -c "import ipaddress; import sys; start=ipaddress.IPv6Address('$start'); end=ipaddress.IPv6Address('$end'); nets=list(ipaddress.summarize_address_range(start, end)); [print(str(net)) for net in nets]" >>/tmp/asn-processed-ipv6.txt
    done
done
