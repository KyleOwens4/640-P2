import argparse
import time
from datetime import datetime
import os
import socket
import struct


class PacketInfo:
    def __init__(self, seq_num, pack_len, packet):
        self.seq_num = seq_num
        self.pack_len = pack_len
        self.packet = packet
        self.attempts = 1

    def addAttempt(self):
        self.attempts += 1

def get_args():
    parser = argparse.ArgumentParser(usage="sender.py -p <port> -g <requester port> -r <rate> -q <seq_no> -l <length>")

    parser.add_argument('-p', choices=range(2050, 65536), type=int,
                        help='Port number the sender should wait for requests on', required=True)
    parser.add_argument('-g', choices=range(2050, 65536), type=int,
                        help='Port the requestor is waiting on', required=True)
    parser.add_argument('-r', type=int, help='Packets to be sent per second', required=True)
    parser.add_argument('-q', type=int, help='Initial sequence of the packet exchange', required=True)
    parser.add_argument('-l', type=int, help='Length of packet payload in bytes', required=True)
    parser.add_argument('-f', type=str, help='Host name of the emulator', required=True)
    parser.add_argument('-e', choices=range(2050, 65536), type=int, help='the port of the emulator.', required=True)
    parser.add_argument('-i', choices=range(1, 4), type=int, help='Priority level to send packets at.', required=True)
    parser.add_argument('-t', type=int, help='Timeout for retransmission for lost packs in milliseconds', required=True)

    return parser.parse_args()


def create_sender_socket(listen_port):
    sender_address = (socket.gethostbyname(socket.gethostname()), listen_port)
    sender_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sender_socket.bind(sender_address)

    return sender_socket


def deconstruct_header(header):
    req_type, seq, data_len = struct.unpack("!cII", header)

    return str(req_type, 'UTF-8'), seq, data_len


def await_file_request(sender_socket, req_sock_num):
    full_packet, requester_address = sender_socket.recvfrom(5500)
    header = full_packet[:9]
    filename = full_packet[9:].decode()

    requester_address = (requester_address[0], req_sock_num)

    return requester_address, header, filename


def print_packet_info(requester_address, seq_num, pack_len, payload, pack_type):
    print(pack_type, "Packet")
    print('send time:      ', datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3])
    print('requester addr: ', requester_address[0] + ':' + str(requester_address[1]))
    print('sequence:       ', seq_num)
    print('length:         ', pack_len)
    print('payload:        ', payload.decode()[:4])
    print()

    return int(time.time() * 1000)


def await_acks(data_dict, sender_socket, timeout, requester_address, packet_rate):
    sender_socket.settimeout(0)
    start_time = int(time.time() * 1000)

    while len(data_dict) > 0:
        time_since_start = int(time.time() * 1000) - start_time

        try:
            full_packet, requester_address = sender_socket.recvfrom(5500)
            header = full_packet[:9]
            pack_type, seq_num, pack_len = deconstruct_header(header)

            if pack_type == 'A':
                del data_dict[seq_num]

        except BlockingIOError as e:
            pass

        if time_since_start > timeout:
            for key in list(data_dict.keys()):
                pack_info = data_dict[key]
                if pack_info.attempts >= 6:
                    print("ERROR: Attempted sending packet with sequence number " + str(pack_info.seq_num)
                          + " six total times without acknowledgement. Packet dropped.")
                    print("")
                    del data_dict[key]
                else:
                    pack_info.attempts += 1
                    send_time = int(time.time() * 1000)
                    sender_socket.sendto(pack_info.packet, requester_address)

                    while int(time.time() * 1000) < send_time + packet_rate:
                        pass



def send_file(sender_socket, requester_address, filename, window_len, args):
    data_dict = {}
    filename = './sender/' + filename
    try:
        file = open(filename, 'r')
    except IOError:
        print(f"{filename} does not exist in this folder")
        exit(-1)

    packet_rate = 1000 / args.r
    seq_num = 1
    rem_file_size = os.path.getsize(filename)

    while rem_file_size > 0:
        for window in range(window_len):
            if rem_file_size <= 0:
                break

            pack_len = rem_file_size if rem_file_size < args.l else args.l
            header = struct.pack("!cII", 'D'.encode('ascii'), socket.htonl(seq_num), pack_len)
            data = file.read(args.l).encode()
            packet = header + data

            data_dict[seq_num] = PacketInfo(seq_num, pack_len, packet)

            send_time = print_packet_info(requester_address, seq_num, pack_len, data, 'DATA')
            sender_socket.sendto(packet, requester_address)

            while int(time.time() * 1000) < send_time + packet_rate:
                pass

            seq_num += 1
            rem_file_size -= pack_len

        await_acks(data_dict, sender_socket, args.t, requester_address, packet_rate)

    packet = struct.pack("!cII", 'E'.encode('ascii'), socket.htonl(seq_num), 0)
    print_packet_info(requester_address, seq_num, 0, ''.encode(), 'END')
    sender_socket.sendto(packet, requester_address)


if __name__ == '__main__':
    args = get_args()

    sender_socket = create_sender_socket(args.p)
    requester_address, requester_header, requested_filename = await_file_request(sender_socket, args.g)
    pack_type, seq_num, window_len = deconstruct_header(requester_header)

    send_file(sender_socket, requester_address, requested_filename, window_len, args)



