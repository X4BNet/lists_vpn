#!perl -lp0a
$_=join$\,sort map{1x(s/\d*./unpack B8,chr$&/ge>4?$&:32)&$_}@F;1while s/^(.*)
\1.*/$1/m||s/^(.*)0
\1.$/$1/m;s!^.*!(join'.',map{ord}split'',pack B32,$&).'/'.length$&!gme