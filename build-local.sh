#!/usr/bin/env bash
# Build VPN and datacenter network lists from ASN data.

set -Eeuo pipefail

export LC_ALL=C

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly INPUT_DIR_DEFAULT="$SCRIPT_DIR/input"
readonly HELPER="$SCRIPT_DIR/helpers/asn_to_cidr.py"
readonly CLEANUP_HELPER="$SCRIPT_DIR/helpers/cleanup.pl"

family="all"
list="all"
output_dir=""
database_dir=""
database_source="iptoasn"
input_dir="$INPUT_DIR_DEFAULT"
work_dir=""

usage() {
    cat <<'EOF'
Usage: ./build-local.sh --output-dir DIR [options]

Builds the VPN and datacenter IPv4 and IPv6 CIDR lists from ASN data.

Options:
  --family ipv4|ipv6|all  Address family to build (default: all)
  --list vpn|datacenter|all
                            Category to build (default: all)
  --output-dir DIR          Empty destination directory for generated files
  --database-source iptoasn|iplocate
                            ASN database provider (default: iptoasn)
  --database-dir DIR        Use local databases instead of downloading:
                            iptoasn: ip2asn-v4.tsv and ip2asn-v6.tsv
                            iplocate: ip-to-asn.csv or ip-to-asn.csv.zip
  --input-dir DIR           Input data root (default: ./input; useful for tests)
  -h, --help                Show this help text

When datacenter is built, its ASN selection includes the VPN ASN selection.
ASN files accept AS12345 includes and -AS12345 exclusions. Selected parent ranges
include unlisted children. Exclusions apply to their own category, override manual
networks as well as ASN includes, and are applied after prefix filtering.
IPLocate builds also read optional category Keywords.txt files. Keywords match
name, org, or domain case-insensitively; -keyword excludes matching ranges.
The destination contains category files and, when datacenter IPv4 is selected,
a root-level ipv4.txt compatibility alias.
EOF
}

die() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

cleanup_work_dir() {
    if [[ -n "$work_dir" && -d "$work_dir" ]]; then
        rm -rf -- "$work_dir"
    fi
}

while (($#)); do
    case "$1" in
        --family)
            (($# >= 2)) || die "--family requires a value"
            family="$2"
            shift 2
            ;;
        --list)
            (($# >= 2)) || die "--list requires a value"
            list="$2"
            shift 2
            ;;
        --output-dir)
            (($# >= 2)) || die "--output-dir requires a value"
            output_dir="$2"
            shift 2
            ;;
        --database-dir)
            (($# >= 2)) || die "--database-dir requires a value"
            database_dir="$2"
            shift 2
            ;;
        --database-source)
            (($# >= 2)) || die "--database-source requires a value"
            database_source="$2"
            shift 2
            ;;
        --input-dir)
            (($# >= 2)) || die "--input-dir requires a value"
            input_dir="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "unknown option: $1"
            ;;
    esac
done

case "$family" in
    ipv4|ipv6|all) ;;
    *) die "--family must be ipv4, ipv6, or all" ;;
esac

case "$list" in
    vpn|datacenter|all) ;;
    *) die "--list must be vpn, datacenter, or all" ;;
esac

case "$database_source" in
    iptoasn|iplocate) ;;
    *) die "--database-source must be iptoasn or iplocate" ;;
esac

[[ -n "$output_dir" ]] || die "--output-dir is required"
[[ -d "$input_dir" ]] || die "input directory does not exist: $input_dir"
[[ -f "$HELPER" ]] || die "missing helper: $HELPER"
[[ -f "$CLEANUP_HELPER" ]] || die "missing helper: $CLEANUP_HELPER"

if [[ -e "$output_dir" ]] && [[ -n "$(find "$output_dir" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    die "output directory must be empty: $output_dir"
fi
mkdir -p "$output_dir"

command -v python3 >/dev/null || die "python3 is required"
if [[ "$family" == "ipv4" || "$family" == "all" ]]; then
    command -v perl >/dev/null || die "perl is required for IPv4 compatibility cleanup"
fi
if [[ -z "$database_dir" ]]; then
    command -v curl >/dev/null || die "curl is required when --database-dir is not supplied"
    if [[ "$database_source" == "iptoasn" ]]; then
        command -v gzip >/dev/null || die "gzip is required for IPtoASN downloads"
    fi
else
    [[ -d "$database_dir" ]] || die "database directory does not exist: $database_dir"
fi

work_dir="$(mktemp -d "${TMPDIR:-/tmp}/lists-vpn-build.XXXXXX")"
trap cleanup_work_dir EXIT

prepare_iplocate_database() {
    if [[ -n "$database_dir" ]]; then
        for database_file in "$database_dir/ip-to-asn.csv" "$database_dir/ip-to-asn.csv.zip"; do
            if [[ -s "$database_file" ]]; then
                printf '%s\n' "$database_file"
                return
            fi
        done
        die "missing or empty IPLocate database in: $database_dir"
    fi

    printf 'Downloading IPLocate combined IPv4/IPv6 database...\n' >&2
    local archive="$work_dir/ip-to-asn.csv.zip"
    # The repository uses Git LFS; raw.githubusercontent.com returns a pointer.
    curl --fail --location --retry 3 --retry-all-errors --output "$archive" \
        "https://media.githubusercontent.com/media/iplocate/ip-address-databases/main/ip-to-asn/ip-to-asn.csv.zip"
    [[ -s "$archive" ]] || die "downloaded IPLocate database is empty"
    printf '%s\n' "$archive"
}

download_database() {
    local family_name="$1"
    local database_file="$work_dir/ip2asn-${family_name}.tsv"
    local archive="$database_file.gz"

    if [[ -n "$database_dir" ]]; then
        database_file="$database_dir/ip2asn-${family_name}.tsv"
        [[ -s "$database_file" ]] || die "missing or empty database: $database_file"
        printf '%s\n' "$database_file"
        return
    fi

    printf 'Downloading IPtoASN %s database...\n' "$family_name" >&2
    curl --fail --location --retry 3 --retry-all-errors --output "$archive" \
        "https://iptoasn.com/data/ip2asn-${family_name}.tsv.gz"
    gzip -t "$archive"
    gzip -dc "$archive" > "$database_file"
    [[ -s "$database_file" ]] || die "downloaded database is empty: $family_name"
    printf '%s\n' "$database_file"
}

collect_manual_networks() {
    local family_name="$1"
    local category="$2"
    local destination="$3"
    local ips_dir="$input_dir/$category/ips"

    : > "$destination"
    [[ -d "$ips_dir" ]] || return

    if [[ "$family_name" == "ipv4" ]]; then
        while IFS= read -r -d '' source_file; do
            awk 'substr($0, 1, 1) != "#" && NF { print $1 }' "$source_file" >> "$destination"
        done < <(find "$ips_dir" -type f -name '*.txt' ! -iname '*ipv6*.txt' -print0 | sort -z)
    else
        while IFS= read -r -d '' source_file; do
            awk 'substr($0, 1, 1) != "#" && NF { print $1 }' "$source_file" >> "$destination"
        done < <(find "$ips_dir" -type f -iname '*ipv6*.txt' -print0 | sort -z)
    fi
}

build_ipv4_output() {
    local category="$1"
    local raw_asn="$work_dir/${category}-ipv4-asn.txt"
    local compacted_asn="$work_dir/${category}-ipv4-asn-compacted.txt"
    local filtered_asn="$work_dir/${category}-ipv4-asn-filtered.txt"
    local manual="$work_dir/${category}-ipv4-manual.txt"
    local combined="$work_dir/${category}-ipv4-combined.txt"
    local destination="$work_dir/output/$category/ipv4.txt"

    # ASN-derived ranges come directly from Python's ipaddress module, so this
    # intermediate normalization can use the fast canonicalizer safely.  Keep
    # the final cleanup below in Perl for legacy manual-input compatibility.
    python3 "$HELPER" normalize --family 4 --output "$compacted_asn" "$raw_asn"
    awk -F/ '$2 ~ /^[0-9]+$/ && $2 <= 24 { print }' "$compacted_asn" > "$filtered_asn"
    collect_manual_networks ipv4 "$category" "$manual"
    cat "$filtered_asn" "$manual" | sort -n > "$combined"
    mkdir -p "$(dirname "$destination")"
    perl "$CLEANUP_HELPER" "$combined" > "$destination"
}

build_ipv6_output() {
    local category="$1"
    local raw_asn="$work_dir/${category}-ipv6-asn.txt"
    local filtered_asn="$work_dir/${category}-ipv6-asn-filtered.txt"
    local manual="$work_dir/${category}-ipv6-manual.txt"
    local destination="$work_dir/output/$category/ipv6.txt"

    awk -F/ '$2 ~ /^[0-9]+$/ && $2 <= 64 { print }' "$raw_asn" > "$filtered_asn"
    collect_manual_networks ipv6 "$category" "$manual"
    mkdir -p "$(dirname "$destination")"
    python3 "$HELPER" normalize --family 6 --output "$destination" "$filtered_asn" "$manual"
}

families=()
case "$family" in
    ipv4) families=(ipv4) ;;
    ipv6) families=(ipv6) ;;
    all) families=(ipv4 ipv6) ;;
esac

categories=()
case "$list" in
    vpn) categories=(vpn) ;;
    datacenter) categories=(datacenter) ;;
    all) categories=(vpn datacenter) ;;
esac

if [[ "$database_source" == "iplocate" ]]; then
    keyword_args=()
    for category in vpn datacenter; do
        if [[ -f "$input_dir/$category/Keywords.txt" ]]; then
            keyword_args+=("--${category}-keywords" "$input_dir/$category/Keywords.txt")
        fi
    done
    iplocate_database="$(prepare_iplocate_database)"
    printf 'Selecting IPLocate ASN and keyword ranges for requested families in one database pass...\n' >&2
    python3 "$HELPER" expand-iplocate --family "$family" --list "$list" \
        --database "$iplocate_database" --vpn-asns "$input_dir/vpn/ASN.txt" \
        --datacenter-asns "$input_dir/datacenter/ASN.txt" --output-dir "$work_dir" "${keyword_args[@]}"
fi

for family_name in "${families[@]}"; do
    if [[ "$family_name" == "ipv4" ]]; then
        family_number=4
    else
        family_number=6
    fi
    if [[ "$database_source" == "iptoasn" ]]; then
        if [[ "$family_name" == "ipv4" ]]; then
            database_file="$(download_database v4)"
        else
            database_file="$(download_database v6)"
        fi
        helper_args=(
            expand-asns
            --family "$family_number"
            --database "$database_file"
            --database-source "$database_source"
            --vpn-asns "$input_dir/vpn/ASN.txt"
            --datacenter-asns "$input_dir/datacenter/ASN.txt"
        )
        if [[ "$list" == "vpn" || "$list" == "all" ]]; then
            helper_args+=(--vpn-output "$work_dir/vpn-${family_name}-asn.txt")
            helper_args+=(--vpn-exclusions-output "$work_dir/vpn-${family_name}-exclusions.txt")
        fi
        if [[ "$list" == "datacenter" || "$list" == "all" ]]; then
            helper_args+=(--datacenter-output "$work_dir/datacenter-${family_name}-asn.txt")
            helper_args+=(--datacenter-exclusions-output "$work_dir/datacenter-${family_name}-exclusions.txt")
        fi
        printf 'Selecting %s ASN ranges in one database pass...\n' "$family_name" >&2
        python3 "$HELPER" "${helper_args[@]}"
    fi

    for category in "${categories[@]}"; do
        if [[ "$family_name" == "ipv4" ]]; then
            build_ipv4_output "$category"
        else
            build_ipv6_output "$category"
        fi
        exclusions="$work_dir/${category}-${family_name}-exclusions.txt"
        if [[ -s "$exclusions" ]]; then
            destination="$work_dir/output/$category/${family_name}.txt"
            python3 "$HELPER" exclude --family "$family_number" --input "$destination" \
                --exclusions "$exclusions" --output "$destination.excluded"
            mv "$destination.excluded" "$destination"
        fi
    done
done

for category in "${categories[@]}"; do
    mkdir -p "$output_dir/$category"
    for family_name in "${families[@]}"; do
        cp "$work_dir/output/$category/${family_name}.txt" "$output_dir/$category/${family_name}.txt"
    done
done

if [[ ( "$list" == "datacenter" || "$list" == "all" ) && ( "$family" == "ipv4" || "$family" == "all" ) ]]; then
    cp "$work_dir/output/datacenter/ipv4.txt" "$output_dir/ipv4.txt"
fi

if [[ "$database_source" == "iplocate" ]]; then
    cat > "$output_dir/ASN-DATABASE.txt" <<'EOF'
IP address data powered by IPLocate.io: https://www.iplocate.io
Source: https://github.com/iplocate/ip-address-databases
ASN database license: Creative Commons Attribution-ShareAlike 4.0 International
https://creativecommons.org/licenses/by-sa/4.0/
Changes: selected configured ASNs and keywords, converted/filtered/merged ranges, added manual networks.
These experimental outputs use IPLocate data; the repository's MIT notice alone
does not describe the upstream database license. Review distribution terms before publishing.
EOF
fi

printf 'Generated output in %s\n' "$output_dir" >&2
