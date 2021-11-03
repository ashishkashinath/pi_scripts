### Some helper scripts to work with Raspberry Pi ###


#### Steps to Prepare Pi before deploying Real-time applications

- Make sure WiFi details are updated on /etc/wpa_supplicant/wpa_supplicant.conf
- sudo apt update -y; sudo apt upgrade -y;
- mkdir Repositories/;mkdir scripts/
- cd Repositories/;git clone https://github.com/ptpd/ptpd.git;
- sudo apt install autotools-dev libpcap0.8-dev autoconf libtool -y; pip install dpkt;
- cd ptpd/;
- sudo autoreconf -vi; sudo ./configure; sudo make; sudo make install;
- cd ~/scripts; git clone -b pi_scripts --single-branch https://github.com/gopchandani/qos_synthesis.git .; 
- sudo apt install tcpdump vim -y; sudo reboot
- sudo raspi-config and make sure GUI is turned off and it boots automatically to command-line
- Add the following lines to /etc/rc.local **before exit 0**
  * sudo ifconfig eth0 <static IP> netmask 255.255.255.0
  * sleep 1
  * sudo ~/scripts/arp_table_fix.sh
  * sudo ~/scripts/powersave_governor.sh
- Run the application. This should generate a PCAP on the server Pi in the home folder
- python3 scripts/write_csv_from_pcap.py
- pscp -pw <password of server Pi> pi@<wireless IP of server Pi>:~/<name of csv file> <local location>

