# This is to be added at the end of the bashrc file

# At the master
sudo taskset 0x2 sudo ptpd2 --interface eth0 --masteronly --unicast -u <Address of slave> --debug --foreground --verbose

# At the slave
