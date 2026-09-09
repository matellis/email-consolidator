# Consolidation notes

## 2026-03-02 19:10 Checkpoint 1: inventory
Sources: /Volumes/OldMac (2019 iMac Time Machine), /mnt/nas/backups/outlook
kind      count      bytes
emlx      412,338    9,812,441,002
mbox      14         2,411,009,331
ost       1          12,884,901,888
Not mounted: the 2011 laptop drive (clicking; will image with ddrescue first).

## 2026-03-03 21:40 Checkpoint 2: gather
applemail/2019-imac  source 431,120 files 9.9G  archive 431,120 files 9.9G  rsync --checksum clean
takeout/2026-01      source 14 files 2.3G       archive 14 files 2.3G
outlook/work.ost     1 file 12G                 1 file 12G  sha1 matches

## 2026-03-04 20:05 Checkpoint 3: normalize
applemail/2019-imac  emlx 412,338  ok 412,301  skip 37 (all truncated .partial.emlx from 2019-09 crash)  counts 412,301
takeout/2026-01      From-lines 96,114  ok 96,114  skip 0
outlook/work.ost     readpst files 58,220  ok 58,220  skip 0
sample 500 applemail: failed=0
