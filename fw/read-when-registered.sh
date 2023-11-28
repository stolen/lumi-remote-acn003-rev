python TlsrPgm.py -p /dev/ttyUSB0 -t 100 -a 100 -s fsw 0
python TlsrPgm.py -p /dev/ttyUSB0 -t 100 -a 100 -s rf 0 0x018470 ../aqara-dump.bin.p1
python TlsrPgm.py -p /dev/ttyUSB0 -t 100 -a 100 -s rf 0x018470 0x00041130 ../aqara-dump.bin.p2
python TlsrPgm.py -p /dev/ttyUSB0 -t 100 -a 100 -s rf 0x0595a0 0x026A60  ../aqara-dump.bin.p3
cat ../aqara-dump.bin.p1 ../aqara-dump.bin.p2 ../aqara-dump.bin.p3 > ../aqara-dump.bin
rm ../aqara-dump.bin.p1 ../aqara-dump.bin.p2 ../aqara-dump.bin.p3
