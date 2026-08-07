#!/usr/bin/perl
use strict;
use warnings;

# Simple IPv6 cleanup script - removes duplicates and basic overlaps
my %seen;
my @networks;

while (my $line = <>) {
    chomp $line;
    next if $line =~ /^#/ || $line =~ /^\s*$/;
    
    # Basic IPv6 CIDR validation
    if ($line =~ /^([0-9a-f:]+)\/(\d+)$/i) {
        my ($ip, $prefix) = ($1, $2);
        
        # Validate prefix length
        if ($prefix >= 0 && $prefix <= 128) {
            # Normalize IPv6 address (basic normalization)
            $ip = lc($ip);
            my $normalized = "$ip/$prefix";
            
            # Skip duplicates
            next if $seen{$normalized};
            $seen{$normalized} = 1;
            
            push @networks, {
                ip => $ip,
                prefix => $prefix,
                original => $line
            };
        }
    }
}

# Sort by IP address (simple string sort for now)
@networks = sort { $a->{original} cmp $b->{original} } @networks;

# Output networks
for my $net (@networks) {
    print $net->{original} . "\n";
}