#!/bin/bash

# Variables
VPNInput="/tmp/vpn_subnets.txt"
VPNOutput="/tmp/vpn_ips.txt"
DatacenterInput="/tmp/datacenter_subnets.txt"
DatacenterOutput="/tmp/datacenter_ips.txt"

# Check if prips is Installed
if ! [ -x "$(command -v prips)" ]; then
  echo && echo " [-] Error: Please install 'prips' before running this script." && echo
  exit 1
fi

# Wordcount
echo && echo " [+] Converting Subnets to IPs..."

# Download List
wget -q -N https://raw.githubusercontent.com/X4BNet/lists_vpn/main/output/vpn/ipv4.txt -O $VPNInput
wget -q -N https://raw.githubusercontent.com/X4BNet/lists_vpn/main/output/datacenter/ipv4.txt -O $DatacenterInput

# Check
echo > $VPNOutput && echo > $DatacenterOutput

while IFS= read -r subnet; do
  prips "$subnet" >> $VPNOutput
done < $VPNInput
sed -i '1d' $VPNOutput

while IFS= read -r subnet; do
  prips "$subnet" >> $DatacenterOutput
done < $DatacenterInput
sed -i '1d' $DatacenterOutput

# Wordcount
echo && echo " [+] VPN Subnet/IP Per File" && echo && wc -l /tmp/vpn_*
echo && echo " [+] Datacenter Subnet/IP Per File" && echo && wc -l /tmp/datacenter_* && echo

exit 0
