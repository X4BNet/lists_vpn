# VPN & datacenter IPs
This is a list of common VPN providers. There are lots of lists of open proxies and tor nodes on the web, but surprisingly few usable ones dedicated to VPN providers and datacenters. This list combines:

  - Known VPN netblocks
  - ASNs owned by datacenters and VPN providers

This list doesn't list _all_ VPNs, but should list the vast majority of common ones. 

## Lists

- **output/vpn/ipv4.txt:** this list is strictly just known VPN networks. A small overlap with Datacenter networks is possible (e.g if it isnt possible to seperate) however most datacenters will not be in this list
- **output/datacenter/ipv4.txt:** this list is for VPNs and Datacenters. Anything that is "not an eyeball network" directly.
- **ipv4.txt:** This is a legacy path for the datacenters list (to be removed in the future, use the above)

## Conversions

- **helpers/subnet-to-ip-expansion.sh:** Converting IPv4 subnets to pure IPv4 addresses

# How to contribute

Please open an issue if you know a VPN provider not listed here _and_ have documentation / evidence. Contributions of data are welcome.

If you wish to improve the automation, a PR is also welcome.

This generation of IP addresses is automated by GitHub Actions CI and rebuilt from the source data regularly. Because the source data is primarily ASNs the data should be accurate for a long period of time.

# Credits

This list was inspired by ejrv and their manually curated list. 
