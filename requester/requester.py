import argparse
from datetime import datetime
import time
import os
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


def get_args():
    parser = argparse.ArgumentParser(usage="sender.py -p <port> -g <requester port> -r <rate> -q <seq_no> -l <length>")

    parser.add_argument('-p', choices=range(2050, 65536), type=int,
                        help='Port number on which to wait for packets', required=True)
    parser.add_argument('-o', type=str,
                        help='Name of the file being requested', required=True)
    parser.add_argument('-f', type=str, help='Host name of the emulator', required=True)
    parser.add_argument('-e', choices=range(2050, 65536), type=int, help='the port of the emulator.', required=True)
    parser.add_argument('-w', type=int, help='Requester\'s window size', required=True)

    return parser.parse_args()


def load_file_table(filename):
    file_locations = {}

    try:
        file = open('./requester/tracker.txt', 'r')
    except IOError as e:
        print(str(e))
        exit(-1)

    lines = file.readlines()
    for line in lines:
        cols = line.split(' ')

        if cols[0] == filename:
            file_locations[int(cols[1])] = (socket.gethostbyname(cols[2]), int(cols[3].strip()))

    return file_locations


def open_listening_socket(socket_num):
    listen_address = (socket.gethostbyname(socket.gethostname()), socket_num)

    new_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    new_socket.bind(listen_address)
    new_socket.settimeout(20)

    return new_socket


def deconstruct_header(header):
    req_type, seq, data_len = struct.unpack("!cII", header)

    return str(req_type, 'UTF-8'), socket.ntohl(seq), data_len


def send_request_packet(requester_socket, filename, address, window_size):
    header = struct.pack("!cII", 'R'.encode('ascii'), 0, window_size)
    packet = header + filename.encode()
    requester_socket.sendto(packet, address)


def send_ack_packet(requester_socket, address, seq_num):
    header = struct.pack("!cII", 'A'.encode('ascii'), seq_num, 0)
    packet = header
    requester_socket.sendto(packet, address)


# def print_packet_info(sender_address, seq_num, pack_len, payload, pack_type):
#     print(pack_type, "Packet")
#     print('send time:      ', datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3])
#     print('sender addr:    ', sender_address[0] + ':' + str(sender_address[1]))
#     print('sequence:       ', seq_num)
#     print('length:         ', pack_len)
#     print('payload:        ', payload.decode()[:4])
#     print()


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
        data = packets[key][1]
        file.write(data.decode())

    file.close()


def request_file(socket_num, filename, window_size):
    requester_socket = open_listening_socket(socket_num)
    packets = {}
    senders = []
    for i in range(1, len(file_table) + 1):
        sender_stats = SenderStats()
        send_request_packet(requester_socket, filename, file_table[i], window_size)
        pack_type = "TBD"

        start_time = int(time.time() * 1000)
        while pack_type != 'E':
            try:
                packet, sender_address = requester_socket.recvfrom(5300)
            except TimeoutError:
                print('Detected lost packet after 20 seconds. Please try again')
                exit(-1)

            pack_type, seq_num, pack_len = deconstruct_header(packet[:9])
            data = packet[9:]
            data = data if len(data) > 0 else ''.encode()

            sender_stats.address = sender_address

            sender_stats.bytes_rec += pack_len

            if pack_type != 'E' and seq_num != 2:
                packets[seq_num] = (i, data)
                sender_stats.packets_rec += 1
                send_ack_packet(requester_socket, file_table[i], seq_num)

        sender_stats.test_duration = int(time.time() * 1000) - start_time
        senders.append(sender_stats)

    print_sender_stats(senders)
    write_file(packets, filename)


if __name__ == '__main__':
    args = get_args()
    file_table = load_file_table(args.o)

    if len(file_table) == 0:
        print("File was not found in the tracker")
        exit(-1)

    request_file(args.p, args.o, args.w)

