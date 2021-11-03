# This is to be added at the end of the bashrc file

# At the master
sudo taskset 0x2 sudo ptpd2 --interface eth0 --masteronly --unicast -u <Address of Slave> --debug --foreground --verbose

# At the slave
sudo taskset 0x2 sudo ptpd2 --interface eth0 --slaveonly --unicast -u <Address of Master> --debug --foreground --verbose
