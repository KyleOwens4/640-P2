import argparse
from datetime import datetime
import time
import socket
import struct


class SenderStats:
    def __init__(self):
        self.address = ''
        self.packets_rec = 0
        self.bytes_rec = 0
        self.test_duration = 0

    def get_average_packets_per_second(self):
        return round(self.packets_rec / (self.test_duration / 1000))


class Packet:
    def __init__(self, packet):
        outer_header = packet[:17]
        inner_header = packet[17:26]

        self.priority, self.src_ip, self.src_port, self.dest_ip, self.dest_port, self.outer_length = struct.unpack("!BIHIHI", outer_header)
        self.type, self.seq_num, self.length = struct.unpack("!cII", inner_header)
        self.type = str(self.type, 'UTF-8')
        self.seq_num = socket.ntohl(self.seq_num)

        self.data = packet[26:]
        self.data = self.data.decode() if len(self.data) > 0 else ''

        self.sender_address = (self.convert_int_to_ip(self.src_ip), self.src_port)

        if args.d:
            self.print_debug_info()

    def convert_int_to_ip(self, int_ip):
        return socket.inet_ntoa(struct.pack('!L', int_ip))

    def print_packet_info(self):
        print('END', "Packet")
        print('send time:      ', datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3])
        print('sender addr:    ', self.sender_address[0] + ':' + str(self.sender_address[1]))
        print('sequence:       ', self.seq_num)
        print('length:         ', self.length)
        print('payload:        ', self.data[:4])
        print()

    def print_debug_info(self):
        print('==============INCOMING PACKET===============')
        print('Priority         ' + str(self.priority))
        print('Source IP        ' + str(self.src_ip))
        print('Source Port      ' + str(self.src_port))
        print('Destination IP   ' + str(self.dest_ip))
        print('Destination Port ' + str(self.dest_port))
        print('Outer Packet Len ' + str(self.outer_length))
        print('Type             ' + str(self.type))
        print('Sequence Number  ' + str(self.seq_num))
        print('Inner Packet Len ' + str(self.length))
        print('Data:            ' + str(self.data[:4]))
        print('Requester Addr   ' + str(self.sender_address[0]))
        print('Requester Port   ' + str(self.sender_address[1]))
        print('============================================')
        print('')

class RequestSocket:
    def __init__(self, listening_port_num, filename, window_size, file_table, emulator_address):
        self.listen_address = (socket.gethostbyname(socket.gethostname()), listening_port_num)
        self.emulator_address = emulator_address

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(self.listen_address)
        self.socket.settimeout(20)

        self.filename = filename
        self.window_size = window_size
        self.file_table = file_table

    def convert_ip_to_int(self, ip_string):
        return struct.unpack("!L", socket.inet_aton(ip_string))[0]

    def create_outer_header(self, file_portion):
        int_src_ip = self.convert_ip_to_int(self.listen_address[0])
        int_dest_ip = self.convert_ip_to_int(file_table[file_portion][0])
        src_port = self.listen_address[1]
        dest_port = file_table[file_portion][1]

        return struct.pack("!BIHIHI", 1, int_src_ip, src_port, int_dest_ip, dest_port, 9)

    def send_request_packet(self, file_portion):
        inner_header = struct.pack("!cII", 'R'.encode('ascii'), 0, self.window_size)
        inner_packet = inner_header + self.filename.encode()

        outer_header = self.create_outer_header(file_portion)
        packet = outer_header + inner_packet

        self.socket.sendto(packet, emulator_address)

    def send_ack_packet(self, file_portion, seq_num):
        inner_header = struct.pack("!cII", 'A'.encode('ascii'), socket.htonl(seq_num), 0)
        outer_header = self.create_outer_header(file_portion)

        packet = outer_header + inner_header
        self.socket.sendto(packet, emulator_address)

    def await_data(self):
        packet, sender_address = self.socket.recvfrom(5300)
        return Packet(packet)


def get_args():
    parser = argparse.ArgumentParser(usage="requester.py -p <port> -o <file option> -f <f_hostname> -e <f_port> "
                                           "-w <window>")

    parser.add_argument('-p', choices=range(2050, 65536), type=int,
                        help='Port number on which to wait for packets', required=True)
    parser.add_argument('-o', type=str,
                        help='Name of the file being requested', required=True)
    parser.add_argument('-f', type=str, help='Host name of the emulator', required=True)
    parser.add_argument('-e', choices=range(2050, 65536), type=int, help='the port of the emulator.', required=True)
    parser.add_argument('-w', type=int, help='Requester\'s window size', required=True)
    parser.add_argument('-d', type=bool, default=False, help='Debug mode', required=False)

    return parser.parse_args()


def load_file_table(filename):
    file_locations = {}

    try:
        file = open('tracker.txt', 'r')
    except IOError as e:
        print(str(e))
        exit(-1)

    lines = file.readlines()
    for line in lines:
        cols = line.split(' ')

        if cols[0] == filename:
            file_locations[int(cols[1])] = (socket.gethostbyname(cols[2]), int(cols[3].strip()))

    return file_locations


def print_sender_stats(senders):
    print('----------Summary----------')
    for sender in senders:
        print('sender addr:            ', sender.address[0] + ':' + str(sender.address[1]))
        print('Total Data packets:     ', sender.packets_rec)
        print('Total Data bytes:       ', sender.bytes_rec)
        print('Average packets/second: ', sender.get_average_packets_per_second())
        print('Duration of the test:   ', sender.test_duration, 'ms')
        print()


def write_file(packets, filename):
    file = open(filename, 'w')
    sorted_keys = list(packets.keys())
    sorted_keys.sort()

    for key in sorted_keys:
        data = packets[key]
        file.write(data)

    file.close()


def request_file(request_socket):
    file_data = {}
    senders = []

    for file_portion in range(1, len(file_table) + 1):
        sender_stats = SenderStats()
        start_time = int(time.time() * 1000)

        request_socket.send_request_packet(file_portion)
        while True:
            try:
                packet = request_socket.await_data()
            except TimeoutError:
                print('Detected lost packet after 20 seconds. Please try again')
                exit(-1)

            if packet.convert_int_to_ip(packet.dest_ip) == request_socket.listen_address[0] \
                    and packet.dest_port == request_socket.listen_address[1]:
                sender_stats.address = packet.sender_address
                sender_stats.bytes_rec += packet.length

                if packet.type == 'E':
                    packet.print_packet_info()
                    break

                if packet.type != 'E':
                    file_data[(file_portion, packet.seq_num)] = packet.data
                    sender_stats.packets_rec += 1
                    request_socket.send_ack_packet(file_portion, packet.seq_num)

        sender_stats.test_duration = int(time.time() * 1000) - start_time
        senders.append(sender_stats)

    print_sender_stats(senders)
    write_file(file_data, request_socket.filename)


if __name__ == '__main__':
    args = get_args()
    file_table = load_file_table(args.o)

    if len(file_table) == 0:
        print("File was not found in the tracker")
        exit(-1)

    emulator_address = (socket.gethostbyname(args.f), args.e)
    request_socket = RequestSocket(args.p, args.o, args.w, file_table, emulator_address)
    request_file(request_socket)

