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

- Converting IPv4 subnets to pure IPv4 addresses [example](https://github.com/sysvar/lists_vpn/blob/main/helpers/subnet-to-ip-expansion.sh).

# How to contribute

Please open an issue if you know a VPN provider not listed here _and_ have documentation / evidence. Contributions of data are welcome.

If you wish to improve the automation, a PR is also welcome.

This generation of IP addresses is automated by GitHub Actions CI and rebuilt from the source data regularly. Because the source data is primarily ASNs the data should be accurate for a long period of time.

# Credits

This list was inspired by ejrv and their manually curated list. 

# License

Software in the below license corresponds to the scripts, automation, and the list itself (source files and generated output).

```
MIT License

Copyright (c) 2024 X4B (Mathew Heard)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```