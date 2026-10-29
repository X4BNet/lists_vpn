# VPN & datacenter IPs

This is a list of common VPN providers. There are lots of lists of open proxies and tor nodes on the web, but surprisingly few usable ones dedicated to VPN providers and datacenters. This list combines:

- Known VPN netblocks
- ASNs owned by datacenters and VPN providers

This list doesn't list _all_ VPNs, but should list the vast majority of common ones.

## Lists

### IPv4

- **output/vpn/ipv4.txt:** this list is strictly just known VPN networks. A small overlap with Datacenter networks is possible (e.g if it isnt possible to seperate) however most datacenters will not be in this list
- **output/datacenter/ipv4.txt:** this list is for VPNs and Datacenters. Anything that is "not an eyeball network" directly.
- **ipv4.txt:** This is a legacy path for the datacenters list (this is scheduled for removal in 2027).

### IPv6

- **output/vpn/ipv6.txt:** IPv6 networks for known VPN providers.
- **output/datacenter/ipv6.txt:** IPv6 networks for VPNs and datacenters combined.

## Conversions

- Converting IPv4 subnets to pure IPv4 addresses [example](https://github.com/sysvar/lists_vpn/blob/main/helpers/subnet-to-ip-expansion.sh).

# How to contribute

Please open an issue if you know a VPN provider not listed here _and_ have documentation / evidence. Contributions of data are welcome.

If you wish to improve the automation, a PR is also welcome.

This generation of IP addresses is automated by GitHub Actions CI and rebuilt from the source data regularly. Because the source data is primarily ASNs the data should be accurate for a long period of time. To build locally, use `./build-local.sh --output-dir DIR`.

## ASN database

We use the [IPLocate IP to ASN database](https://github.com/iplocate/ip-address-databases/tree/main/ip-to-asn)
to map the configured ASNs to IPv4 and IPv6 ranges. IP address data powered by
[IPLocate.io](https://www.iplocate.io).

IPLocate is the default database source. To build the lists:

```sh
./build-local.sh --output-dir /tmp/lists-vpn-iplocate-output
```

The builder downloads the combined IPv4/IPv6 ZIP once and streams its CSV without
extracting it. One CSV pass selects both families and any explicit exclusions;
normalization merges integer intervals to limit memory use.
Selected parent prefixes include their child ranges, even when a
more specific child belongs to an ASN that is not listed.
For repeatable offline builds, pass `--database-dir DIR` containing
`ip-to-asn.csv.zip` or `ip-to-asn.csv` (CSV takes precedence). IPtoASN offline builds
use `ip2asn-v4.tsv` and `ip2asn-v6.tsv`. Both sources use the same ASN selections,
manual inputs, and prefix filters. The destination must be empty.

ASN files accept explicit exclusions:

```text
AS15169   # Include this ASN's ranges, including children
-AS12345  # Exclude this ASN's ranges, even inside an included parent
```

Exclusions win over all includes and manual networks. They are applied after
prefix filtering, so an exclusion can leave precise holes smaller than `/24` or
`/64`. An exclusion applies only to the category whose `ASN.txt` contains it.
Datacenter inherits VPN includes; it does not inherit VPN exclusions. Both
database providers support exclusions, using the ranges present in that provider's
database. IPtoASN's flat ranges cannot restore a parent prefix omitted upstream.

IPLocate builds also select entries using literal, case-insensitive substring
matches in the CSV's `name`, `org`, or `domain` fields. Keywords are configured in
`input/vpn/Keywords.txt` (initially `VPN`) and
`input/datacenter/Keywords.txt` (`Host` and `Huawei`), one keyword per line:

```text
VPN          # Include matching entries, even if their ASN is not listed
-Example VPN # Exclude entries containing this phrase
```

Blank lines and `#` comments are ignored. Matching any positive keyword includes
the entry's network; matching a negative keyword excludes it, overriding ASN,
keyword, and manual includes. Keyword exclusions apply only to their category;
datacenter inherits VPN keyword includes. Matching is per CSV entry, so it does
not automatically include or exclude other networks belonging to the same ASN.
Keyword files are optional for custom input directories. IPtoASN builds use only
ASN and manual rules. Scheduled builds explicitly select IPLocate.

Compare two complete builds by address coverage, including added/removed CIDRs:

```sh
python3 helpers/compare_outputs.py --baseline /tmp/lists-vpn-iptoasn-output \
  --candidate /tmp/lists-vpn-iplocate-output --output-dir /tmp/lists-vpn-comparison
```

The upstream IPLocate database is licensed under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). IPLocate builds
include `ASN-DATABASE.txt` with source attribution and upstream license details.
This repository's scripts, curated inputs, and generated lists are licensed under
MIT, as set out below. Upstream sources retain their own licenses.

# Credits

This list was inspired by ejrv and their manually curated list.

# License

The scripts, automation, curated source files, and generated IP lists produced by
this project are licensed under the MIT License. Upstream database licenses are
identified in the ASN database section above.

```
MIT License

Copyright (c) 2026 X4B (Mathew Heard)

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
